"""Guard for pull requests opened directly (not through the submission form).

Runs from .github/workflows/pr-guard.yml on `pull_request_target`. It never
checks out or executes code from the pull request: it reads metadata and file
contents through the API and parses YAML with ``yaml.safe_load`` only.

Environment: GITHUB_EVENT_PATH, GITHUB_REPOSITORY, GH_TOKEN.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml

from common import REPO_URL, load_policy
from github_api import GitHub, GitHubError, neutralize
from policy import identity_key, links_in, url_problems
from trust import assess

MARKER = "<!-- trading-awesome-bot:pr-guard -->"
SENSITIVE_PREFIXES = (".github/", "scripts/", "tests/")
SENSITIVE_FILES = {"LICENSE", "SECURITY.md", "CODE_OF_CONDUCT.md", "CONTRIBUTING.md"}
MAX_ENTRY_BYTES = 20_000
AFFILIATED_RE = re.compile(r"^- \[[xX]\] I work for, own, or was paid", re.M)


def entry_urls(data: dict) -> list[str]:
    urls = [data["url"]] if isinstance(data.get("url"), str) else []
    for key in ("api", "pricing", "description", "deprecation_note"):
        if isinstance(data.get(key), str):
            urls += [target for _, target in links_in(data[key])]
    return urls


def load_entry(text: str | None) -> dict | None:
    if text is None or len(text.encode()) > MAX_ENTRY_BYTES:
        return None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def run(event: dict, gh: GitHub, *, dry_run: bool) -> int:
    pr = event["pull_request"]
    number, author = pr["number"], pr["user"]["login"]
    if pr["user"].get("type") == "Bot":
        print("Pull request opened by an app; skipping.")
        return 0
    if pr.get("state") != "open":
        return 0

    files = gh.pull_files(number)
    paths = [f["filename"] for f in files]
    adds_entry = any(f["status"] == "added" and f["filename"].startswith("data/entries/") for f in files)
    policy = load_policy()
    trust = assess(gh, policy, author, pr.get("author_association", "NONE"),
                   kind="new_entry" if adds_entry else "update", check_limits=False)
    if trust.maintainer:
        print("Maintainer pull request; skipping.")
        return 0

    problems: list[str] = []
    notes: list[str] = []
    labels: set[str] = set()
    close = False

    if not trust.ok:
        problems += trust.errors
        labels.add("trust-check-failed")
        close = True
    elif adds_entry and not trust.trusted:
        problems.append(
            "New entries from first-time contributors must go through the "
            f"[submission form]({REPO_URL}/issues/new?template=new-entry.yml). The form runs the same checks "
            "and opens a pull request for you.")
        labels.add("use-submission-form")
        close = True

    sensitive = [p for p in paths if p.startswith(SENSITIVE_PREFIXES) or p in SENSITIVE_FILES]
    if sensitive:
        labels.add("sensitive-change")
        notes.append("This pull request changes automation or policy files ("
                     + ", ".join(f"`{neutralize(p)}`" for p in sensitive[:10])
                     + "); it needs a maintainer review.")

    head_repo = (pr.get("head") or {}).get("repo") or {}
    for f in files:
        name = f["filename"]
        if not (name.startswith("data/entries/") and name.endswith(".yml")) or f["status"] == "removed":
            continue
        head = load_entry(gh.file_at(head_repo.get("full_name", gh.repo), name, pr["head"]["sha"]))
        if head is None:
            problems.append(f"`{neutralize(name)}` is not a valid entry file.")
            continue
        for url in entry_urls(head):
            for problem in url_problems(url):
                problems.append(f"`{neutralize(name)}`: {neutralize(url)} {problem}.")
        base_name = f.get("previous_filename") or name
        if f["status"] in ("modified", "renamed"):
            base = load_entry(gh.file_at(gh.repo, base_name, pr["base"]["sha"]))
            if base and isinstance(base.get("url"), str) and isinstance(head.get("url"), str):
                before, after = identity_key(base["url"]), identity_key(head["url"])
                if before != after:
                    labels.add("domain-change")
                    notes.append(
                        f"`{neutralize(name)}` moves the website from `{before}` to `{after}`. Per the "
                        f"[link-change policy]({REPO_URL}/blob/main/CONTRIBUTING.md#link-and-domain-changes), "
                        "please show that the new domain belongs to the same organization: the old site "
                        "redirects there, or link an official announcement.")

    if AFFILIATED_RE.search(pr.get("body") or ""):
        labels.add("vendor-submitted")
    if trust.flags:
        labels.add("needs-manual-review")

    print(json.dumps({"problems": problems, "notes": notes, "labels": sorted(labels), "close": close}, indent=2))
    if dry_run:
        return 0
    if labels:
        gh.add_labels(number, sorted(labels))
    if problems or notes:
        body = []
        if problems:
            body += ["### Problems", *[f"- {p}" for p in problems], ""]
        if notes:
            body += ["### Notes for reviewers", *[f"- {n}" for n in notes], ""]
        if close:
            body.append("This pull request was closed automatically. If you think this is a mistake, "
                        "comment here and a maintainer will take a look.")
        gh.upsert_comment(number, MARKER, "\n".join(body))
    if close:
        gh.set_state(number, "closed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--event", default=os.environ.get("GITHUB_EVENT_PATH"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.event:
        parser.error("--event or GITHUB_EVENT_PATH is required")
    event = json.loads(Path(args.event).read_text(encoding="utf-8"))
    gh = GitHub(os.environ.get("GITHUB_REPOSITORY", "lentrade/trading-awesome"))
    try:
        return run(event, gh, dry_run=args.dry_run)
    except GitHubError as exc:
        print(f"GitHub API error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
