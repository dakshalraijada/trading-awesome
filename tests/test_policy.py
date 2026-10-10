import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from policy import identity_key, registrable_domain, style_problems, text_problems, url_problems  # noqa: E402


class UrlPolicyTest(unittest.TestCase):
    def test_clean_url_passes(self):
        self.assertEqual(url_problems("https://docs.example.com/api/v2?lang=en"), [])

    def test_requires_https(self):
        self.assertIn("must use https://", url_problems("http://example.com/"))

    def test_rejects_tracking_and_referral_parameters(self):
        for url in (
            "https://example.com/?utm_source=github",
            "https://example.com/signup?ref=abc",
            "https://example.com/?aff_id=7",
            "https://example.com/?inviteCode=XYZ",
            "https://example.com/?fbclid=1",
        ):
            with self.subTest(url=url):
                self.assertTrue(any("tracking/referral" in p for p in url_problems(url)))

    def test_rejects_referral_paths(self):
        self.assertTrue(url_problems("https://exchange.example/ref/ABC123"))
        self.assertTrue(url_problems("https://exchange.example/invite/ABC123"))

    def test_rejects_shorteners_punycode_ip_and_credentials(self):
        self.assertTrue(url_problems("https://bit.ly/abc"))
        self.assertTrue(url_problems("https://xn--bnance-3ya.com/"))
        self.assertTrue(url_problems("https://192.168.0.1/"))
        self.assertTrue(url_problems("https://user:pass@example.com/"))
        self.assertTrue(url_problems("https://example.com:8443/"))

    def test_rejects_hidden_unicode(self):
        self.assertTrue(url_problems("https://example.com/‮exe.txt"))


class DomainTest(unittest.TestCase):
    def test_registrable_domain(self):
        self.assertEqual(registrable_domain("docs.example.com"), "example.com")
        self.assertEqual(registrable_domain("www.example.co.uk"), "example.co.uk")
        self.assertEqual(registrable_domain("acme.github.io"), "acme.github.io")
        self.assertEqual(registrable_domain("kafka.apache.org"), "kafka.apache.org")

    def test_identity_key_uses_path_on_code_hosts(self):
        self.assertEqual(identity_key("https://github.com/ccxt/ccxt/tree/master/python"), "github.com/ccxt/ccxt")
        self.assertEqual(identity_key("https://www.example.com/pricing"), "example.com")


class TextPolicyTest(unittest.TestCase):
    def test_table_breaking_text(self):
        self.assertTrue(text_problems("a | b", allow_links=False))
        self.assertTrue(text_problems("line\nbreak", allow_links=False))
        self.assertTrue(text_problems("<script>x</script>", allow_links=False))
        self.assertTrue(text_problems("![img](https://example.com/x.png)", allow_links=True))

    def test_links_only_where_allowed(self):
        text = "Docs at [docs](https://example.com/)."
        self.assertEqual(text_problems(text, allow_links=True), [])
        self.assertTrue(text_problems(text, allow_links=False))
        self.assertTrue(text_problems("See [x](https://example.com/?ref=me)", allow_links=True))
        self.assertTrue(text_problems("Bare https://example.com link", allow_links=True))

    def test_style(self):
        self.assertEqual(style_problems("REST API for U.S. equities data."), [])
        self.assertTrue(style_problems("The best API for traders."))
        self.assertTrue(style_problems("Guaranteed profits"))
        self.assertTrue(style_problems("Fast API!"))


if __name__ == "__main__":
    unittest.main()
