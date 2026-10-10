"""Shared helpers for the Trading Awesome data pipeline.

Every entry of the list lives in ``data/entries/<slug>.yml``. The README tables
are generated from those files by ``build_readme.py``; nothing in this module
talks to the network.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ENTRIES_DIR = DATA_DIR / "entries"
CATEGORIES_FILE = DATA_DIR / "categories.yml"
README_FILE = ROOT / "README.md"
TEMPLATES_DIR = ROOT / ".github" / "ISSUE_TEMPLATE"
POLICY_FILE = ROOT / ".github" / "submission-policy.yml"

REPO_SLUG = "lentrade/trading-awesome"
REPO_URL = f"https://github.com/{REPO_SLUG}"

# Field order used when an entry is written back to disk.
ENTRY_FIELDS = (
    "name",
    "url",
    "category",
    "description",
    "scope",
    "api",
    "pricing",
    "repo",
    "status",
    "deprecation_note",
    "affiliation",
    "added",
    "last_verified",
)
REQUIRED_FIELDS = (
    "name",
    "url",
    "category",
    "description",
    "scope",
    "api",
    "pricing",
    "added",
    "last_verified",
)
STATUSES = ("active", "deprecated")
AFFILIATIONS = ("none", "vendor", "other")

COVERAGE_LABELS = (
    "Crypto — spot / on-chain / DeFi",
    "Crypto — derivatives",
    "Traditional markets",
    "Forex / FX",
    "Brokerage / execution",
    "Research / automation",
)

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class Category:
    id: str
    number: int
    title: str

    @property
    def heading(self) -> str:
        return f"{self.number}. {self.title}"

    @property
    def anchor(self) -> str:
        return github_anchor(self.heading)


@dataclass
class Entry:
    path: Path
    data: dict[str, Any]

    @property
    def slug(self) -> str:
        return self.path.stem

    @property
    def name(self) -> str:
        return str(self.data.get("name", ""))


def github_anchor(heading: str) -> str:
    """Reproduce GitHub's heading-anchor algorithm for plain-text headings."""
    text = heading.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "entry"


def sort_key(name: str) -> str:
    return unicodedata.normalize("NFKC", name).casefold()


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_categories() -> list[Category]:
    raw = load_yaml(CATEGORIES_FILE) or []
    return [Category(id=c["id"], number=int(c["number"]), title=c["title"]) for c in raw]


def load_entries(directory: Path = ENTRIES_DIR) -> list[Entry]:
    entries = []
    for path in sorted(directory.glob("*.yml")):
        data = load_yaml(path)
        entries.append(Entry(path=path, data=data if isinstance(data, dict) else {}))
    return entries


def load_policy() -> dict[str, Any]:
    return load_yaml(POLICY_FILE) or {}


def as_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            return None
    return None


class _EntryDumper(yaml.SafeDumper):
    # Equal values (e.g. added == last_verified) must not become YAML anchors/aliases.
    def ignore_aliases(self, data: Any) -> bool:
        return True


def dump_entry(data: dict[str, Any]) -> str:
    """Serialize an entry with a stable key order and one value per line."""
    ordered = {key: data[key] for key in ENTRY_FIELDS if key in data and data[key] not in (None, "")}
    for key in data:
        if key not in ordered and data[key] not in (None, ""):
            ordered[key] = data[key]
    return yaml.dump(ordered, Dumper=_EntryDumper, sort_keys=False, allow_unicode=True, width=10_000)


def write_entry(path: Path, data: dict[str, Any]) -> None:
    path.write_text(dump_entry(data), encoding="utf-8", newline="\n")


def today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()
