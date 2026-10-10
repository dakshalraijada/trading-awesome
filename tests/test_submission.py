import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from common import TEMPLATES_DIR, load_entries  # noqa: E402
from issue_forms import form_fields, parse  # noqa: E402
from submission import build_new_entry, build_update  # noqa: E402

NEW_ENTRY = TEMPLATES_DIR / "new-entry.yml"
UPDATE_ENTRY = TEMPLATES_DIR / "update-entry.yml"


def issue_body(template: Path, values: dict) -> str:
    """Render an issue body the way GitHub does for a submitted form."""
    parts = []
    for f in form_fields(template):
        value = values.get(f.id)
        if f.type == "checkboxes":
            checked = value or []
            text = "\n".join(f"- [{'X' if opt in checked else ' '}] {opt}" for opt in f.options)
        else:
            text = value if value else "_No response_"
        parts.append(f"### {f.label}\n\n{text}")
    return "\n\n".join(parts)


def all_confirmations(template: Path) -> list[str]:
    return next(f.options for f in form_fields(template) if f.id == "confirmations")


VALID = {
    "name": "Acme Market Data",
    "url": "https://acme-market-data.example/",
    "category": "Traditional markets, macro & multi-asset data",
    "description": "REST and WebSocket API for U.S. equities and options data with official Python and Go clients.",
    "scope_detail": "U.S. equities / options",
    "coverage": ["Traditional markets", "Research / automation"],
    "api_docs": "https://docs.acme-market-data.example/",
    "packages": "Python: official https://github.com/acme/acme-python\nGo: community https://github.com/someone/acme-go\n"
                "MCP: https://github.com/acme/acme-mcp",
    "pricing": "Free tier; paid plans start at **$29/month**.",
    "pricing_url": "https://acme-market-data.example/pricing",
    "affiliation": "I work for, own, or was paid or asked by this service",
    "notes": "Fills a gap: exchange-sourced options data with a free tier and official SDKs.",
    "confirmations": all_confirmations(NEW_ENTRY),
}


class FormParsingTest(unittest.TestCase):
    def test_round_trip(self):
        form = parse(issue_body(NEW_ENTRY, VALID), NEW_ENTRY)
        self.assertEqual(form["name"], VALID["name"])
        self.assertEqual(form["api_docs"], VALID["api_docs"])
        self.assertTrue(form["coverage"]["Traditional markets"])
        self.assertFalse(form["coverage"]["Forex / FX"])
        self.assertEqual(form["repo"], "")

    def test_injected_heading_cannot_overwrite_earlier_field(self):
        values = dict(VALID, description="Data API.\n### Service name\nEvil")
        form = parse(issue_body(NEW_ENTRY, values), NEW_ENTRY)
        self.assertEqual(form["name"], VALID["name"])
        self.assertIn("### Service name", form["description"])


class NewEntryTest(unittest.TestCase):
    def setUp(self):
        self.entries = load_entries()

    def build(self, **overrides):
        form = parse(issue_body(NEW_ENTRY, dict(VALID, **overrides)), NEW_ENTRY)
        return build_new_entry(form, {}, None, self.entries, online=False)

    def test_valid_submission(self):
        out = self.build()
        self.assertEqual(out.errors, [])
        self.assertEqual(out.slug, "acme-market-data")
        self.assertEqual(out.data["category"], "market-data")
        self.assertEqual(out.data["scope"], "U.S. equities / options; Traditional markets; Research / automation")
        self.assertEqual(
            out.data["api"],
            "[API docs](https://docs.acme-market-data.example/) · Py: [official](https://github.com/acme/acme-python)"
            " · Go: [community](https://github.com/someone/acme-go) · PHP: — · [MCP](https://github.com/acme/acme-mcp)",
        )
        self.assertEqual(out.data["pricing"], "Free tier; paid plans start at **$29/month**; see "
                                              "[official pricing](https://acme-market-data.example/pricing).")
        self.assertEqual(out.data["affiliation"], "vendor")
        self.assertIn("vendor-submitted", out.labels)

    def test_duplicate_name_and_site(self):
        out = self.build(name="alpaca", url="https://alpaca.markets/")
        self.assertTrue(any("already on the list" in e for e in out.errors))
        self.assertTrue(any("already listed" in e for e in out.errors))

    def test_rejects_referral_links_and_marketing(self):
        out = self.build(url="https://acme-market-data.example/?ref=abc",
                         description="The best market data API ever!")
        joined = " ".join(out.errors)
        self.assertIn("tracking/referral", joined)
        self.assertIn("promotional", joined)

    def test_requires_coverage_and_pricing_source(self):
        out = self.build(coverage=[], pricing_url="")
        joined = " ".join(out.errors)
        self.assertIn("Coverage labels", joined)
        self.assertIn("Pricing source URL", joined)

    def test_open_source_needs_no_pricing_url(self):
        out = self.build(pricing="Open source.", pricing_url="")
        self.assertEqual(out.errors, [])

    def test_rejects_registry_package_links_and_mentions(self):
        out = self.build(packages="Python: official https://pypi.org/project/acme/",
                         description="Data API maintained by @someone.")
        joined = " ".join(out.errors)
        self.assertIn("not registry pages", joined)
        self.assertIn("`@`", joined)

    def test_unchecked_confirmations(self):
        out = self.build(confirmations=[])
        self.assertTrue(any("Confirmations" in e for e in out.errors))


class UpdateTest(unittest.TestCase):
    def setUp(self):
        self.entries = load_entries()

    def build(self, **values):
        base = {"entry": "Alpaca", "affiliation": "I have no affiliation with this service",
                "confirmations": all_confirmations(UPDATE_ENTRY), "source": "https://alpaca.markets/pricing"}
        form = parse(issue_body(UPDATE_ENTRY, {**base, **values}), UPDATE_ENTRY)
        return build_update(form, {}, self.entries, online=False)

    def test_pricing_update(self):
        out = self.build(change="Pricing", value="Market data from **$99/month**.")
        self.assertEqual(out.errors, [])
        self.assertEqual(out.data["pricing"], "Market data from **$99/month**; see "
                                              "[official pricing](https://alpaca.markets/pricing).")

    def test_domain_change_is_flagged(self):
        out = self.build(change="Website URL", value="https://alpaca-new.example/")
        self.assertEqual(out.errors, [])
        self.assertIn("domain-change", out.labels)

    def test_unknown_entry(self):
        out = self.build(entry="Nonexistent Service", change="Pricing", value="Free.")
        self.assertTrue(out.errors)

    def test_something_else_is_manual(self):
        out = self.build(change="Something else", value="Please move it to section 4.")
        self.assertTrue(out.manual)


if __name__ == "__main__":
    unittest.main()
