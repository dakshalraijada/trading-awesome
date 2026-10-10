"""Turn issue-form submissions into pull requests (IssueOps).

Runs from .github/workflows/submission.yml on `issues` events. The issue body
is untrusted input: it is parsed here in Python and never reaches a shell.

Flow:
  1. Contributor trust checks (account age, rate limits, blocklist).
  2. Offline content policy (URL hygiene, wording, duplicates).
  3. Online checks (links resolve, no cross-domain redirects, domain age, repo health).
  4. On success, write data/entries/<slug>.yml to branch submission/issue-<n> and
     open or update a pull request. A maintainer always reviews and merges by hand.

Environment: GITHUB_EVENT_PATH, GITHUB_REPOSITORY, GH_TOKEN (GitHub App token).
Use --dry-run with a saved event file to see what would happen without writing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from build_readme import TABLE_HEADER, render_row
from common import (
    COVERAGE_LABELS,
    REPO_URL,
    TEMPLATES_DIR,
    Entry,
    dump_entry,
    load_categories,
    load_entries,
    load_policy,
    slugify,
    sort_key,
    today,
)
from github_api import GitHub, GitHubError, neutralize
from issue_forms import parse
from netcheck import domain_registered, fetch, repo_health
from policy import (
    CODE_HOSTS,
    PRIVATE_SUFFIXES,
    identity_key,
    registrable_domain,
    style_problems,
    text_problems,
    url_problems,
)
from trust import TrustResult, assess, label_applied_by_maintainer

MARKER = "<!-- trading-awesome-bot:submission -->"
OVERRIDE_LABEL = "maintainer-approved"
REPO_RE = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$")
PACKAGE_RE = re.compile(r"^(?P<lang>[A-Za-z#.+ ]+?)\s*:\s*(?:(?P<kind>official|community)\s+)?(?P<url>\S+)$", re.I)
LANGUAGES = {
    "python": "Py", "py": "Py", "go": "Go", "golang": "Go", "php": "PHP",
    "javascript": "JS", "js": "JS", "node": "JS", "node.js": "JS", "typescript": "TS", "ts": "TS",
    "rust": "Rust", "java": "Java", "c#": "C#", "csharp": "C#", ".net": "C#", "r": "R", "mcp": "MCP",
}
PACKAGE_HOSTS = {"github.com", "gitlab.com", "codeberg.org"}
AFFILIATION_OPTIONS = {
    "I have no affiliation with this service": "none",
    "I work for, own, or was paid or asked by this service": "vendor",
    "Other relationship (explain in notes)": "other",
}
CHANGE_FIELDS = {
    "Pricing": "pricing",
    "Description": "description",
    "Website URL": "url",
    "Markets / scope": "scope",
    "Mark as deprecated or shut down": "status",
    "Something else": None,
}


@dataclass
class Outcome:
    data: dict = field(default_factory=dict)
    slug: str = ""
    title: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    labels: set[str] = field(default_factory=set)
    facts: dict[str, object] = field(default_factory=dict)
    manual: bool = False


def one_line(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def no_mentions(field_name: str, text: str, out: Outcome) -> None:
    if "@" in text:
        out.errors.append(f"**{field_name}** must not contain `@`.")


def check_url_field(label: str, url: str, out: Outcome, *, required: bool) -> bool:
    if not url:
        if required:
            out.errors.append(f"**{label}** is required.")
        return False
    for problem in url_problems(url):
        out.errors.append(f"**{label}** {problem}.")
    return not url_problems(url)


def online_url_check(label: str, url: str, out: Outcome, *, primary: bool = False) -> None:
    result = fetch(url)
    if result.broken:
        out.errors.append(f"**{label}** could not be loaded ({neutralize(result.describe())}).")
    elif result.unverifiable:
        out.warnings.append(f"**{label}** answered {result.describe()}; a maintainer will verify it manually.")
    if result.final_url and result.moved_domain:
        message = (f"**{label}** redirects to another domain (`{neutralize(result.final_url)}`). "
                   f"Submit the final destination URL.")
        (out.errors if primary else out.warnings).append(message)


def domain_age_check(url: str, policy: dict, out: Outcome) -> None:
    host = (urlsplit(url).hostname or "").lower()
    domain = registrable_domain(host)
    if domain in CODE_HOSTS or ".".join(domain.split(".")[-2:]) in PRIVATE_SUFFIXES:
        return
    registered = domain_registered(domain)
    min_age = int(policy.get("min_domain_age_days", 90))
    if registered is None:
        out.warnings.append(f"Could not determine when `{domain}` was registered; a maintainer will check.")
        out.labels.add("needs-manual-review")
        return
    age = (today() - registered).days
    out.facts["domain registered"] = registered.isoformat()
    if age < min_age:
        out.errors.append(f"`{domain}` was registered {age} days ago. Services must have a domain at least "
                          f"{min_age} days old to be listed.")


def blocked_domain(url: str, policy: dict) -> bool:
    domain = registrable_domain(urlsplit(url).hostname or "")
    return domain in {d.lower() for d in policy.get("blocked_domains") or []}


def render_packages(api_docs: str, raw: str, out: Outcome) -> str:
    slots: dict[str, str] = {}
    extras: list[str] = []
    for line in [ln.strip() for ln in raw.splitlines() if ln.strip()]:
        m = PACKAGE_RE.match(line)
        lang = LANGUAGES.get(m.group("lang").strip().lower()) if m else None
        if not m or not lang:
            out.errors.append(f"**SDKs and packages**: cannot parse `{neutralize(line)}`. "
                              f"Use `Language: official https://github.com/owner/repo`.")
            continue
        url, kind = m.group("url"), (m.group("kind") or "").lower()
        if not check_url_field(f"Package link for {lang}", url, out, required=True):
            continue
        if lang == "MCP":
            extras.append(f"[MCP]({url})")
            out.facts.setdefault("packages", []).append(url)
            continue
        if registrable_domain(urlsplit(url).hostname or "") not in PACKAGE_HOSTS:
            out.errors.append(f"**SDKs and packages**: link source repositories (GitHub, GitLab, Codeberg), "
                              f"not registry pages (`{neutralize(url)}`).")
            continue
        if not kind:
            out.errors.append(f"**SDKs and packages**: say whether the {lang} package is `official` or `community`.")
            continue
        if lang in slots:
            out.errors.append(f"**SDKs and packages**: more than one {lang} package; list the main one.")
            continue
        slots[lang] = f"{lang}: [{kind}]({url})"
        out.facts.setdefault("packages", []).append(url)

    parts = [f"[API docs]({api_docs})"] if api_docs else ["No public API identified"]
    core = ("Py", "Go", "PHP")
    if any(lang in slots for lang in core):
        parts += [slots.get(lang, f"{lang}: —") for lang in core]
    else:
        parts.append("Py/Go/PHP: —")
    parts += [value for lang, value in slots.items() if lang not in core]
    parts += extras
    return " · ".join(parts)


def render_pricing(text: str, source: str) -> str:
    text = one_line(text).rstrip(" .;")
    return f"{text}; see [official pricing]({source})." if source else f"{text}."


def existing_by_identity(entries: list[Entry], url: str) -> Entry | None:
    ident = identity_key(url)
    for entry in entries:
        other = entry.data.get("url")
        if isinstance(other, str) and identity_key(other) == ident:
            return entry
    return None


def build_new_entry(form: dict, policy: dict, gh: GitHub | None, entries: list[Entry], online: bool) -> Outcome:
    out = Outcome()
    categories = {c.title: c for c in load_categories()}

    name = one_line(form.get("name", ""))
    url = one_line(form.get("url", ""))
    description = one_line(form.get("description", ""))
    scope_detail = one_line(form.get("scope_detail", ""))
    api_docs = one_line(form.get("api_docs", ""))
    repo = one_line(form.get("repo", "")).rstrip("/")
    pricing = one_line(form.get("pricing", ""))
    pricing_url = one_line(form.get("pricing_url", ""))
    coverage = [label for label, checked in (form.get("coverage") or {}).items() if checked]

    for problem in text_problems(name, allow_links=False, max_length=60):
        out.errors.append(f"**Service name** {problem}.")
    no_mentions("Service name", name, out)
    if any(sort_key(e.name) == sort_key(name) for e in entries):
        out.errors.append(f"**{neutralize(name)}** is already on the list. Use the update form instead.")

    if check_url_field("Website URL", url, out, required=True):
        if blocked_domain(url, policy):
            out.errors.append("This domain is not accepted on the list.")
        twin = existing_by_identity(entries, url)
        if twin:
            out.errors.append(f"This site is already listed as **{neutralize(twin.name)}**.")

    category = categories.get(form.get("category", ""))
    if not category:
        out.errors.append("**Section** must be one of the listed sections.")

    for problem in text_problems(description, allow_links=False, max_length=250) + style_problems(description):
        out.errors.append(f"**What it does**: {problem}.")
    no_mentions("What it does", description, out)

    if not coverage:
        out.errors.append("**Coverage labels**: pick at least one.")
    if scope_detail:
        for problem in text_problems(scope_detail, allow_links=False, max_length=120):
            out.errors.append(f"**Markets / scope (details)** {problem}.")
        no_mentions("Markets / scope (details)", scope_detail, out)
    scope_parts = [scope_detail] if scope_detail else []
    scope = "; ".join(scope_parts + [c for c in COVERAGE_LABELS if c in coverage])

    if api_docs:
        check_url_field("API documentation URL", api_docs, out, required=False)
    api = render_packages(api_docs, form.get("packages", ""), out)

    if repo and not REPO_RE.match(repo):
        out.errors.append("**Source repository** must look like `https://github.com/owner/repo`.")
    if not repo and REPO_RE.match(url.rstrip("/")):
        repo = url.rstrip("/")

    for problem in text_problems(pricing, allow_links=False, max_length=300):
        out.errors.append(f"**Public pricing** {problem}.")
    no_mentions("Public pricing", pricing, out)
    open_source = "open source" in pricing.lower() or "open-source" in pricing.lower()
    if pricing_url:
        check_url_field("Pricing source URL", pricing_url, out, required=False)
    elif not open_source:
        out.errors.append("**Pricing source URL** is required unless the project is open source.")

    affiliation = AFFILIATION_OPTIONS.get(form.get("affiliation", ""))
    if not affiliation:
        out.errors.append("**Your relationship to this service** must be answered.")
    elif affiliation != "none":
        out.labels.add("vendor-submitted")
    if len(one_line(form.get("notes", ""))) < 30:
        out.errors.append("**Why it belongs on the list**: explain which editorial criteria it meets.")
    unchecked = [label for label, checked in (form.get("confirmations") or {}).items() if not checked]
    if unchecked:
        out.errors.append("Please tick every box under **Confirmations**.")

    if online and not out.errors:
        online_url_check("Website URL", url, out, primary=True)
        domain_age_check(url, policy, out)
        if api_docs:
            online_url_check("API documentation URL", api_docs, out)
        if pricing_url:
            online_url_check("Pricing source URL", pricing_url, out)
        for package_url in out.facts.get("packages", []):
            online_url_check(f"Package `{package_url}`", package_url, out)
        if repo and gh is not None:
            inactive = int((policy.get("maintenance") or {}).get("repo_inactive_days", 365))
            for problem in repo_health(gh, repo, inactive_days=inactive):
                out.errors.append(f"**Source repository**: {problem}.")

    date = today()
    out.slug = slugify(name)
    out.title = f"Add {name}"
    out.data = {
        "name": name, "url": url, "category": category.id if category else "",
        "description": description, "scope": scope, "api": api,
        "pricing": render_pricing(pricing, pricing_url), "repo": repo or None,
        "affiliation": affiliation, "added": date, "last_verified": date,
    }
    return out


def find_entry(entries: list[Entry], name: str) -> Entry | None:
    key = sort_key(one_line(name))
    for entry in entries:
        if sort_key(entry.name) == key or entry.slug == slugify(name):
            return entry
    return None


def build_update(form: dict, policy: dict, entries: list[Entry], online: bool) -> Outcome:
    out = Outcome()
    entry = find_entry(entries, form.get("entry", ""))
    if not entry:
        out.errors.append(f"No entry named **{neutralize(one_line(form.get('entry', '')))}** was found. "
                          f"Copy the name exactly as it appears in the list.")
        return out
    change = form.get("change", "")
    if change not in CHANGE_FIELDS:
        out.errors.append("**What should change** must be one of the listed options.")
        return out
    field_name = CHANGE_FIELDS[change]
    value = one_line(form.get("value", ""))
    source = one_line(form.get("source", ""))
    affiliation = AFFILIATION_OPTIONS.get(form.get("affiliation", ""))
    if not affiliation:
        out.errors.append("**Your relationship to this service** must be answered.")
    elif affiliation != "none":
        out.labels.add("vendor-submitted")
    unchecked = [label for label, checked in (form.get("confirmations") or {}).items() if not checked]
    if unchecked:
        out.errors.append("Please tick every box under **Confirmations**.")

    out.slug = entry.slug
    out.title = f"Update {entry.name}: {change.lower()}"
    out.data = dict(entry.data)
    if field_name is None:
        out.manual = True
        return out

    check_url_field("Source URL", source, out, required=True)
    if not value:
        out.errors.append("**New value** is required.")
        return out

    if field_name == "pricing":
        for problem in text_problems(value, allow_links=False, max_length=300):
            out.errors.append(f"**New value** {problem}.")
        out.data["pricing"] = render_pricing(value, source)
    elif field_name == "description":
        for problem in text_problems(value, allow_links=False, max_length=250) + style_problems(value):
            out.errors.append(f"**New value**: {problem}.")
        out.data["description"] = value
    elif field_name == "scope":
        for problem in text_problems(value, allow_links=False, max_length=200):
            out.errors.append(f"**New value** {problem}.")
        out.data["scope"] = value
    elif field_name == "url":
        if check_url_field("New value", value, out, required=True):
            old_domain = identity_key(entry.data["url"])
            if identity_key(value) != old_domain:
                out.labels.add("domain-change")
                out.warnings.append(
                    f"The website moves from `{old_domain}` to `{identity_key(value)}`. Per the link-change policy, "
                    f"a maintainer must confirm the new domain belongs to the same organization (the old site "
                    f"redirects there, or the source URL is an official announcement).")
                if online:
                    domain_age_check(value, policy, out)
            if blocked_domain(value, policy):
                out.errors.append("This domain is not accepted on the list.")
        out.data["url"] = value
    elif field_name == "status":
        for problem in text_problems(value, allow_links=False, max_length=200):
            out.errors.append(f"**New value** {problem}.")
        out.data["status"] = "deprecated"
        out.data["deprecation_note"] = f"{value.rstrip('.')} ([source]({source}))."
    for text_field in ("description", "scope", "pricing"):
        if field_name == text_field:
            no_mentions("New value", value, out)

    if online and not out.errors:
        online_url_check("Source URL", source, out)
        if field_name == "url":
            online_url_check("New value", value, out, primary=True)
    out.data["last_verified"] = today()
    return out


def trust_failure_comment(trust: TrustResult) -> str:
    reasons = "\n".join(f"- {r}" for r in trust.errors)
    return (
        "### Submission not accepted\n\n"
        f"{reasons}\n\n"
        "These rules protect the list from spam and impersonation; see "
        f"[CONTRIBUTING.md]({REPO_URL}/blob/main/CONTRIBUTING.md#who-can-submit). If you believe this is a mistake, "
        "reply below and a maintainer can review the submission manually."
    )


def problems_comment(out: Outcome) -> str:
    lines = ["### Please fix the following\n"]
    lines += [f"- {e}" for e in out.errors]
    if out.warnings:
        lines += ["", "**Notes**", *[f"- {w}" for w in out.warnings]]
    lines += ["", "Edit this issue to correct the form; the checks run again automatically."]
    return "\n".join(lines)


def pr_body(out: Outcome, issue_number: int, author: str, trust: TrustResult, kind: str) -> str:
    preview = neutralize(render_row(out.data))
    facts = {**trust.facts, **{k: v for k, v in out.facts.items() if k != "packages"}}
    lines = [
        f"{'Adds' if kind == 'new_entry' else 'Updates'} **{neutralize(out.data['name'])}** "
        f"as requested in #{issue_number} by @{author}.",
        "",
        "#### Preview",
        "",
        TABLE_HEADER,
        preview,
        "",
        "#### Automated checks",
        "",
        "- Contributor checks: " + ("overridden by a maintainer" if any("overridden" in f for f in trust.flags)
                                    else "passed"),
        "- Content policy (links, wording, duplicates): passed",
        "- Online checks (reachability, redirects, domain age, repository health): passed",
    ]
    if out.warnings or trust.flags:
        lines += ["", "#### Needs a human look", ""]
        lines += [f"- {w}" for w in out.warnings]
        lines += [f"- Contributor signal: {f}" for f in trust.flags]
    if facts:
        lines += ["", "<details><summary>Facts</summary>", ""]
        lines += [f"- {k}: {neutralize(v)}" for k, v in facts.items()]
        lines += ["", "</details>"]
    affiliation = out.data.get("affiliation")
    if affiliation and affiliation != "none":
        lines += ["", f"> **Disclosure:** the submitter reports a relationship with this service (`{affiliation}`)."]
    lines += ["", "README.md is regenerated automatically after merge.", "", f"Closes #{issue_number}"]
    return "\n".join(lines)


def open_pull_request(gh: GitHub, out: Outcome, issue: dict, trust: TrustResult, kind: str, base: str) -> dict:
    number, author = issue["number"], issue["user"]["login"]
    branch = f"submission/issue-{number}"
    path = f"data/entries/{out.slug}.yml"
    message = (f"{out.title}\n\nSubmitted via #{number}.\n\n"
               f"Co-authored-by: {author} <{issue['user']['id']}+{author}@users.noreply.github.com>")
    base_sha = gh.branch_sha(base)
    existing = gh.branch_sha(branch)
    gh.commit_files(branch, base_sha, {path: dump_entry(out.data)}, message, force=True, create=existing is None)
    body = pr_body(out, number, author, trust, kind)
    pull = gh.open_pull_for(branch)
    if pull:
        gh.update_pull(pull["number"], out.title, body)
    else:
        pull = gh.create_pull(branch, base, out.title, body)
    labels = {"new-entry" if kind == "new_entry" else "update-entry", *out.labels}
    if trust.flags:
        labels.add("needs-manual-review")
    gh.add_labels(pull["number"], sorted(labels))
    return pull


def run(event: dict, gh: GitHub | None, *, online: bool, dry_run: bool) -> int:
    issue = event.get("issue") or {}
    if "pull_request" in issue:
        return 0
    labels = {label["name"] for label in issue.get("labels", [])}
    kind = "new_entry" if "new-entry" in labels else "update" if "update-entry" in labels else None
    if kind is None or "submission" not in labels:
        print("Not a submission issue; nothing to do.")
        return 0
    action = event.get("action")
    if action == "labeled" and (event.get("label") or {}).get("name") != OVERRIDE_LABEL:
        return 0

    number, author = issue["number"], issue["user"]["login"]
    policy = load_policy()
    override = OVERRIDE_LABEL in labels and gh is not None and label_applied_by_maintainer(gh, number, OVERRIDE_LABEL)
    if issue.get("state") == "closed":
        if not (action == "labeled" and override):
            print("Issue is closed; ignoring.")
            return 0
        if not dry_run:
            gh.set_state(number, "open")

    if override:
        trust = TrustResult(login=author, trusted=True, flags=["contributor checks overridden by a maintainer"])
    elif gh is None:
        trust = TrustResult(login=author, trusted=True, flags=["offline dry run: contributor checks skipped"])
    else:
        trust = assess(gh, policy, author, issue.get("author_association", "NONE"), kind=kind, exclude_issue=number)
    if not trust.ok:
        print("Trust checks failed:", *trust.errors, sep="\n- ")
        if not dry_run:
            gh.upsert_comment(number, MARKER, trust_failure_comment(trust))
            gh.add_labels(number, ["trust-check-failed"])
            gh.set_state(number, "closed", "not_planned")
        return 0

    template = TEMPLATES_DIR / ("new-entry.yml" if kind == "new_entry" else "update-entry.yml")
    form = parse(issue.get("body") or "", template)
    entries = load_entries()
    if kind == "new_entry":
        out = build_new_entry(form, policy, gh, entries, online)
    else:
        out = build_update(form, policy, entries, online)

    if out.manual:
        print("Change needs manual handling.")
        if not dry_run:
            gh.upsert_comment(number, MARKER, "Thanks! This kind of change is handled by a maintainer by hand. "
                                              "We will follow up here.")
            gh.add_labels(number, ["needs-manual-review"])
        return 0
    if out.errors:
        print("Content checks failed:", *out.errors, sep="\n- ")
        if not dry_run:
            gh.upsert_comment(number, MARKER, problems_comment(out))
            gh.add_labels(number, ["needs-changes"])
        return 0

    print("Checks passed. Entry:\n" + dump_entry(out.data))
    if dry_run:
        print(pr_body(out, number, author, trust, kind))
        return 0
    base = (event.get("repository") or {}).get("default_branch", "main")
    pull = open_pull_request(gh, out, issue, trust, kind, base)
    gh.remove_label(number, "needs-changes")
    gh.add_labels(number, ["pr-opened"])
    gh.upsert_comment(number, MARKER, f"Checks passed. Pull request: #{pull['number']}. "
                                      f"A maintainer will review it; edits to this issue update the pull request.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--event", default=os.environ.get("GITHUB_EVENT_PATH"), help="path to the event JSON")
    parser.add_argument("--dry-run", action="store_true", help="print the outcome without writing to GitHub")
    parser.add_argument("--offline", action="store_true", help="skip GitHub and network checks (implies --dry-run)")
    args = parser.parse_args()
    if not args.event:
        parser.error("--event or GITHUB_EVENT_PATH is required")
    event = json.loads(Path(args.event).read_text(encoding="utf-8"))
    gh = None if args.offline else GitHub(os.environ.get("GITHUB_REPOSITORY", "lentrade/trading-awesome"))
    try:
        return run(event, gh, online=not args.offline, dry_run=args.dry_run or args.offline)
    except GitHubError as exc:
        print(f"GitHub API error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
