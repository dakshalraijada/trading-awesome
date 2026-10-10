"""Validate data/entries/*.yml, the README markers, and the issue forms.

Usage:
    python scripts/validate.py                    # structural checks for every entry
    python scripts/validate.py --base origin/main # also apply editorial rules to entries
                                                  # changed since the base ref, and reject
                                                  # hand edits to generated README tables

Errors exit with status 1. Warnings are printed but do not fail the run. When
running inside GitHub Actions, findings are emitted as file annotations.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from build_readme import generated_regions, render
from common import (
    AFFILIATIONS,
    ENTRY_FIELDS,
    README_FILE,
    REQUIRED_FIELDS,
    ROOT,
    SLUG_RE,
    STATUSES,
    TEMPLATES_DIR,
    Entry,
    as_date,
    load_categories,
    load_entries,
    load_yaml,
    slugify,
    sort_key,
    today,
)
from policy import identity_key, links_in, style_problems, text_problems, url_problems

MAX_LENGTH = {"name": 60, "description": 400, "scope": 200, "api": 900, "pricing": 600}
NEW_DESCRIPTION_MAX = 250
REPO_RE = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
IN_CI = os.environ.get("GITHUB_ACTIONS") == "true"


class Report:
    def __init__(self) -> None:
        self.errors = 0
        self.warnings = 0

    def _emit(self, level: str, path: Path | None, message: str) -> None:
        rel = path.relative_to(ROOT).as_posix() if path else ""
        if IN_CI:
            location = f" file={rel}" if rel else ""
            print(f"::{level}{location}::{message}")
        else:
            print(f"{level.upper():7} {rel + ': ' if rel else ''}{message}")

    def error(self, path: Path | None, message: str) -> None:
        self.errors += 1
        self._emit("error", path, message)

    def warning(self, path: Path | None, message: str) -> None:
        self.warnings += 1
        self._emit("warning", path, message)


def check_entry(entry: Entry, category_ids: set[str], report: Report) -> None:
    data, path = entry.data, entry.path
    if not data:
        report.error(path, "file is empty or not a YAML mapping")
        return
    if not SLUG_RE.match(entry.slug):
        report.error(path, "file name must be lowercase words separated by hyphens")
    elif entry.slug != slugify(entry.name):
        report.error(path, f"file name should be `{slugify(entry.name)}.yml` to match the entry name")

    for field in REQUIRED_FIELDS:
        if field not in data or data[field] in (None, ""):
            report.error(path, f"missing required field `{field}`")
    for field in data:
        if field not in ENTRY_FIELDS:
            report.error(path, f"unknown field `{field}`")

    for field in ("name", "url", "category", "description", "scope", "api", "pricing", "repo", "deprecation_note"):
        if field in data and not isinstance(data[field], str):
            report.error(path, f"`{field}` must be a string")
            return

    for field, allow_links in (("name", False), ("description", True), ("scope", False), ("api", True),
                               ("pricing", True), ("deprecation_note", True)):
        if field in data:
            for problem in text_problems(data[field], allow_links=allow_links, max_length=MAX_LENGTH.get(field)):
                report.error(path, f"`{field}` {problem}")

    if "url" in data:
        for problem in url_problems(data["url"]):
            report.error(path, f"`url` {problem}")
    if "repo" in data:
        if not REPO_RE.match(data["repo"]):
            report.error(path, "`repo` must look like https://github.com/<owner>/<repo>")
    if data.get("category") not in category_ids:
        report.error(path, f"`category` must be one of: {', '.join(sorted(category_ids))}")
    if data.get("status", "active") not in STATUSES:
        report.error(path, f"`status` must be one of: {', '.join(STATUSES)}")
    if data.get("status") == "deprecated" and not data.get("deprecation_note"):
        report.warning(path, "deprecated entries should explain why in `deprecation_note`")
    if "affiliation" in data and data["affiliation"] not in AFFILIATIONS:
        report.error(path, f"`affiliation` must be one of: {', '.join(AFFILIATIONS)}")

    added, verified = as_date(data.get("added")), as_date(data.get("last_verified"))
    for field, value in (("added", added), ("last_verified", verified)):
        if field in data and value is None:
            report.error(path, f"`{field}` must be a date in YYYY-MM-DD format")
        elif value and value > today():
            report.error(path, f"`{field}` is in the future")
    if added and verified and verified < added:
        report.error(path, "`last_verified` cannot be earlier than `added`")


def check_editorial(entry: Entry, report: Report) -> None:
    """Stricter rules for entries added or changed in the current change set."""
    data, path = entry.data, entry.path
    description = data.get("description", "")
    for problem in style_problems(description):
        report.error(path, problem)
    if len(description) > NEW_DESCRIPTION_MAX:
        report.error(path, f"description is {len(description)} characters; keep new descriptions under {NEW_DESCRIPTION_MAX}")
    if description.lower().startswith(data.get("name", "").lower() + " "):
        report.warning(path, "description should not start by repeating the service name")
    pricing = data.get("pricing", "").lower()
    if "](" not in pricing and not any(w in pricing for w in ("open source", "open-source", "free")):
        report.warning(path, "pricing should link to its source, e.g. `see [official pricing](https://...)`")


def check_collection(entries: list[Entry], report: Report) -> None:
    names: dict[str, Path] = {}
    for entry in entries:
        key = sort_key(entry.name)
        if key in names:
            report.error(entry.path, f"duplicate name, already used by {names[key].name}")
        names[key] = entry.path


def check_same_site(entry: Entry, entries: list[Entry], report: Report) -> None:
    url = entry.data.get("url")
    if not isinstance(url, str) or not url:
        return
    ident = identity_key(url)
    for other in entries:
        if other.path != entry.path and isinstance(other.data.get("url"), str) and identity_key(other.data["url"]) == ident:
            report.warning(entry.path, f"same site as {other.path.name} ({ident}); make sure this is not a duplicate")


def check_readme(categories, report: Report) -> None:
    readme = README_FILE.read_text(encoding="utf-8")
    for category in categories:
        if f"## {category.heading}\n" not in readme:
            report.error(README_FILE, f"missing heading `## {category.heading}`")
        if f"<!-- BEGIN GENERATED:table:{category.id} -->" not in readme:
            report.error(README_FILE, f"missing table marker for `{category.id}`")
        if f"](#{category.anchor})" not in readme:
            report.warning(README_FILE, f"table of contents does not link to #{category.anchor}")


def check_forms(categories, report: Report) -> None:
    titles = [c.title for c in categories]
    for form in sorted(TEMPLATES_DIR.glob("*.yml")):
        if form.name == "config.yml":
            continue
        spec = load_yaml(form) or {}
        for item in spec.get("body", []):
            if item.get("id") == "category":
                options = item.get("attributes", {}).get("options", [])
                if options != titles:
                    report.error(form, "category dropdown must list data/categories.yml titles in order")


def check_online(entry: Entry, report: Report) -> None:
    from netcheck import fetch  # network access only when asked for

    data, path = entry.data, entry.path
    urls = [data["url"]] + [target for key in ("api", "pricing", "description", "deprecation_note")
                            for _, target in links_in(data.get(key, ""))]
    for url in dict.fromkeys(urls):
        result = fetch(url)
        if result.broken:
            report.error(path, f"{url} could not be loaded ({result.describe()})")
        elif result.unverifiable:
            report.warning(path, f"{url} could not be verified automatically ({result.describe()})")
        if url == data["url"] and result.moved_domain:
            report.error(path, f"{url} redirects to another domain ({result.final_url}); list the final URL")


def changed_files(base: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=AMR", f"{base}...HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def base_readme(base: str) -> str | None:
    result = subprocess.run(["git", "show", f"{base}:README.md"], cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8")
    return result.stdout if result.returncode == 0 else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", help="git ref to compare against (enables change-set checks)")
    parser.add_argument("--online", action="store_true", help="with --base, also fetch the links of changed entries")
    args = parser.parse_args()

    report = Report()
    categories = load_categories()
    category_ids = {c.id for c in categories}
    entries = load_entries()

    for entry in entries:
        check_entry(entry, category_ids, report)
    check_collection(entries, report)
    check_readme(categories, report)
    check_forms(categories, report)

    if args.base:
        changed = set(changed_files(args.base))
        for entry in entries:
            if entry.path.relative_to(ROOT).as_posix() in changed:
                check_editorial(entry, report)
                check_same_site(entry, entries, report)
                if args.online:
                    check_online(entry, report)
        if "README.md" in changed:
            before = base_readme(args.base)
            after = README_FILE.read_text(encoding="utf-8")
            if before is not None:
                # A generated region may stay as on the base branch (the bot rebuilds README
                # after merge) or match a fresh render of this branch's data; anything else
                # is a hand edit that the next rebuild would silently discard.
                old, new = generated_regions(before), generated_regions(after)
                fresh = generated_regions(render(after, entries, categories))
                edited = sorted(k for k in new if k in old and new[k] not in (old[k], fresh.get(k)))
                if edited:
                    report.error(README_FILE, "generated tables were edited by hand ("
                                 + ", ".join(edited) + "); edit data/entries/*.yml instead")

    print(f"\n{len(entries)} entries checked: {report.errors} error(s), {report.warnings} warning(s).")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
