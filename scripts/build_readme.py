"""Render the generated parts of README.md from data/entries/*.yml.

Generated regions are delimited by HTML comments, for example::

    <!-- BEGIN GENERATED:table:brokerage -->
    ...
    <!-- END GENERATED:table:brokerage -->

Everything outside those markers is edited by hand.

Usage:
    python scripts/build_readme.py           # rewrite README.md in place
    python scripts/build_readme.py --check   # exit 1 if README.md is out of date
"""

from __future__ import annotations

import argparse
import re
import sys

from common import README_FILE, Category, Entry, as_date, load_categories, load_entries, sort_key

TABLE_HEADER = (
    "| Service | What it does | Markets / scope | API & packages | Public pricing / tariff |\n"
    "| --- | --- | --- | --- | --- |"
)
RECENT_LIMIT = 10
MARKER_RE = re.compile(
    r"(<!-- BEGIN GENERATED:(?P<key>[a-z0-9:-]+) -->)(?P<body>.*?)(<!-- END GENERATED:(?P=key) -->)",
    re.DOTALL,
)


def render_row(data: dict) -> str:
    name = f"**[{data['name']}]({data['url']})**"
    description = data["description"]
    if data.get("status") == "deprecated":
        name = f"~~{name}~~"
        note = data.get("deprecation_note", "").strip()
        description = f"{description} **Deprecated:** {note}" if note else f"{description} **Deprecated.**"
    return f"| {name} | {description} | {data['scope']} | {data['api']} | {data['pricing']} |"


def render_table(entries: list[Entry]) -> str:
    rows = [render_row(e.data) for e in sorted(entries, key=lambda e: sort_key(e.name))]
    return "\n".join([TABLE_HEADER, *rows])


def render_recent(entries: list[Entry], categories: dict[str, Category]) -> str:
    dated = [e for e in entries if as_date(e.data.get("added")) and e.data.get("status") != "deprecated"]
    dated.sort(key=lambda e: (as_date(e.data["added"]), sort_key(e.name)), reverse=True)
    lines = ["| Added | Service | Section |", "| --- | --- | --- |"]
    for entry in dated[:RECENT_LIMIT]:
        category = categories[entry.data["category"]]
        lines.append(
            f"| {as_date(entry.data['added']).isoformat()} | [{entry.name}]({entry.data['url']}) "
            f"| [{category.heading}](#{category.anchor}) |"
        )
    return "\n".join(lines)


def render(readme: str, entries: list[Entry], categories: list[Category]) -> str:
    by_id = {c.id: c for c in categories}
    by_category: dict[str, list[Entry]] = {c.id: [] for c in categories}
    for entry in entries:
        by_category.setdefault(entry.data.get("category"), []).append(entry)
    active = [e for e in entries if e.data.get("status") != "deprecated"]

    seen: set[str] = set()

    def replace(match: re.Match) -> str:
        key = match.group("key")
        seen.add(key)
        kind, _, arg = key.partition(":")
        if kind == "table":
            if arg not in by_id:
                raise SystemExit(f"README marker refers to unknown category '{arg}'")
            body = render_table(by_category[arg])
            return f"{match.group(1)}\n{body}\n{match.group(4)}"
        if kind == "count":
            return f"{match.group(1)}{len(active)}{match.group(4)}"
        if kind == "recent":
            return f"{match.group(1)}\n{render_recent(entries, by_id)}\n{match.group(4)}"
        raise SystemExit(f"Unknown README marker '{key}'")

    result = MARKER_RE.sub(replace, readme)
    missing = [c.id for c in categories if f"table:{c.id}" not in seen]
    if missing:
        raise SystemExit(f"README has no table markers for categories: {', '.join(missing)}")
    return result


def generated_regions(readme: str) -> dict[str, str]:
    return {m.group("key"): m.group("body") for m in MARKER_RE.finditer(readme)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail if README.md is not up to date")
    args = parser.parse_args()

    current = README_FILE.read_text(encoding="utf-8")
    updated = render(current, load_entries(), load_categories())
    if args.check:
        if updated != current:
            print("README.md is out of date. Run: python scripts/build_readme.py", file=sys.stderr)
            return 1
        print("README.md is up to date.")
        return 0
    if updated != current:
        README_FILE.write_text(updated, encoding="utf-8", newline="\n")
        print("README.md regenerated.")
    else:
        print("README.md already up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
