"""Scheduled upkeep for the list.

Commands:
    links           Check every link; report broken links and primary sites that now
                    redirect to a different domain (a common sign of a hijacked or
                    sold domain).
    stale           Report entries not verified recently and source repositories that
                    are archived, missing, or inactive.
    publish-readme  Regenerate README.md and commit it to the default branch if it
                    changed (used after merges, with the GitHub App token).

Reports print to stdout. With --issue, the report is kept in a single tracking
issue that is updated on each run and closed when everything is clean.

Environment for --issue / publish-readme: GITHUB_REPOSITORY, GH_TOKEN.
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from build_readme import render
from common import README_FILE, as_date, load_categories, load_entries, load_policy, today
from github_api import GitHub, GitHubError, neutralize
from netcheck import fetch, repo_health
from policy import links_in

REPORTS = {
    "links": {"label": "link-report", "title": "Link check report"},
    "stale": {"label": "stale-report", "title": "Stale entries report"},
}


def collect_links(entries) -> dict[str, list[tuple[str, bool]]]:
    """url -> [(entry name, is_primary)]"""
    links: dict[str, list[tuple[str, bool]]] = {}
    for entry in entries:
        if entry.data.get("status") == "deprecated":
            continue
        links.setdefault(entry.data["url"], []).append((entry.name, True))
        for key in ("api", "pricing", "description"):
            for _, target in links_in(entry.data.get(key, "")):
                links.setdefault(target, []).append((entry.name, False))
    return links


def links_report(entries) -> tuple[str, bool]:
    links = collect_links(entries)
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = dict(zip(links, pool.map(fetch, links)))

    broken, moved, unverifiable = [], [], []
    for url, result in sorted(results.items(), key=lambda kv: kv[1].url):
        owners = links[url]
        names = ", ".join(sorted({n for n, _ in owners}))
        primary = any(is_primary for _, is_primary in owners)
        if result.broken:
            broken.append(f"| {names} | {'site' if primary else 'link'} | {url} | {neutralize(result.describe())} |")
        elif result.unverifiable:
            unverifiable.append(f"- {names}: {url} ({result.describe()})")
        if primary and result.final_url and result.moved_domain:
            moved.append(f"| {names} | {url} | {neutralize(result.final_url)} |")

    lines = [f"Checked {len(results)} links on {today().isoformat()}.", ""]
    if moved:
        lines += [
            "## Primary site redirects to another domain",
            "",
            "Confirm each move is legitimate (rebrand or acquisition) before updating the entry. "
            "An unexpected redirect can mean the domain was sold, expired, or hijacked; "
            "if in doubt, remove the link first.",
            "",
            "| Entry | Listed URL | Now redirects to |",
            "| --- | --- | --- |",
            *moved,
            "",
        ]
    if broken:
        lines += ["## Broken links", "", "| Entry | Kind | URL | Result |", "| --- | --- | --- | --- |", *broken, ""]
    if unverifiable:
        lines += [
            "<details><summary>Could not verify automatically (bot protection or rate limits): "
            f"{len(unverifiable)}</summary>",
            "",
            *unverifiable,
            "",
            "</details>",
        ]
    if not moved and not broken:
        lines.append("No broken links and no unexpected domain changes.")
    return "\n".join(lines), bool(moved or broken)


def stale_report(entries, gh: GitHub | None) -> tuple[str, bool]:
    policy = (load_policy().get("maintenance") or {})
    stale_after = int(policy.get("stale_after_days", 180))
    inactive_days = int(policy.get("repo_inactive_days", 365))

    stale = []
    for entry in entries:
        verified = as_date(entry.data.get("last_verified"))
        if verified and (today() - verified).days > stale_after and entry.data.get("status") != "deprecated":
            stale.append((verified, entry))
    stale.sort(key=lambda pair: pair[0])

    repo_problems = []
    if gh is not None:
        for entry in entries:
            repo = entry.data.get("repo")
            if repo and entry.data.get("status") != "deprecated":
                problems = repo_health(gh, repo, inactive_days=inactive_days)
                if problems:
                    repo_problems.append(f"| {entry.name} | {repo} | {'; '.join(problems)} |")

    lines = []
    if stale:
        lines += [
            f"## Not verified for more than {stale_after} days",
            "",
            "Re-check pricing and descriptions against the provider's site, then update `last_verified`.",
            "",
            "| Entry | Last verified | File |",
            "| --- | --- | --- |",
            *[f"| {e.name} | {d.isoformat()} | `data/entries/{e.slug}.yml` |" for d, e in stale],
            "",
        ]
    if repo_problems:
        lines += ["## Source repositories needing attention", "",
                  "| Entry | Repository | Problem |", "| --- | --- | --- |", *repo_problems, ""]
    if not lines:
        lines.append("All entries were verified recently and their repositories look active.")
    return "\n".join(lines), bool(stale or repo_problems)


def upsert_report_issue(gh: GitHub, kind: str, body: str, has_findings: bool) -> None:
    meta = REPORTS[kind]
    _, items = gh.search_count(f"repo:{gh.repo} is:issue is:open label:{meta['label']}")
    existing = items[0]["number"] if items else None
    if has_findings:
        if existing:
            gh.request("PATCH", gh.r(f"/issues/{existing}"), {"body": body})
        else:
            gh.request("POST", gh.r("/issues"), {"title": meta["title"], "body": body, "labels": [meta["label"]]})
    elif existing:
        gh.request("PATCH", gh.r(f"/issues/{existing}"), {"body": body})
        gh.set_state(existing, "closed", "completed")


def publish_readme(gh: GitHub, branch: str, base_sha: str) -> int:
    current = README_FILE.read_text(encoding="utf-8")
    updated = render(current, load_entries(), load_categories())
    if updated == current:
        print("README.md is up to date; nothing to publish.")
        return 0
    try:
        gh.commit_files(branch, base_sha, {"README.md": updated}, "Regenerate README from data/entries",
                        force=False, create=False)
    except GitHubError as exc:
        if exc.status == 422:
            print(f"{branch} moved since this run started; the next run will publish the README.")
            return 0
        raise
    print("README.md regenerated and committed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["links", "stale", "publish-readme"])
    parser.add_argument("--issue", action="store_true", help="keep the report in a tracking issue")
    parser.add_argument("--no-github", action="store_true", help="skip checks that need the GitHub API")
    parser.add_argument("--branch", default="main", help="branch for publish-readme")
    parser.add_argument("--base-sha", default=os.environ.get("GITHUB_SHA"), help="commit the README is built from")
    args = parser.parse_args()

    repo = os.environ.get("GITHUB_REPOSITORY", "lentrade/trading-awesome")
    gh = None if args.no_github else GitHub(repo)
    entries = load_entries()

    if args.command == "publish-readme":
        if gh is None or not args.base_sha:
            parser.error("publish-readme needs GitHub access and --base-sha")
        return publish_readme(gh, args.branch, args.base_sha)

    if args.command == "links":
        body, findings = links_report(entries)
    else:
        body, findings = stale_report(entries, gh)
    print(body)
    if args.issue:
        if gh is None:
            parser.error("--issue needs GitHub access")
        upsert_report_issue(gh, args.command, body, findings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
