import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_readme import generated_regions, render, render_row  # noqa: E402
from common import README_FILE, github_anchor, load_categories, load_entries, slugify  # noqa: E402


class BuildTest(unittest.TestCase):
    # README.md is not required to be up to date on a branch: the bot regenerates it
    # after merge. Rendering must still be deterministic.
    def test_render_is_idempotent(self):
        current = README_FILE.read_text(encoding="utf-8")
        once = render(current, load_entries(), load_categories())
        self.assertEqual(render(once, load_entries(), load_categories()), once)

    def test_tables_are_sorted(self):
        regions = generated_regions(README_FILE.read_text(encoding="utf-8"))
        for key, body in regions.items():
            if not key.startswith("table:"):
                continue
            names = [line.split("[", 1)[1].split("]", 1)[0] for line in body.strip().splitlines()[2:]]
            self.assertEqual(names, sorted(names, key=str.casefold), key)

    def test_deprecated_row(self):
        row = render_row({"name": "Old", "url": "https://old.example/", "description": "Did things.",
                          "scope": "Research / automation", "api": "—", "pricing": "—",
                          "status": "deprecated", "deprecation_note": "Shut down in 2026-09."})
        self.assertTrue(row.startswith("| ~~**[Old](https://old.example/)**~~ | Did things. **Deprecated:** Shut down"))

    def test_helpers(self):
        self.assertEqual(slugify("kdb+ / q (Kx)"), "kdb-q-kx")
        self.assertEqual(slugify("LONA™"), "lonatm")
        self.assertEqual(github_anchor("4. Crypto market intelligence & on-chain analytics"),
                         "4-crypto-market-intelligence--on-chain-analytics")


if __name__ == "__main__":
    unittest.main()
