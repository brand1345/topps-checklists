"""Robustness smoke tests against other Topps PDFs. fixtures/ is local-only (gitignored);
these tests are skipped when it is absent (e.g. in CI)."""
import os
import shutil
import tempfile
import unittest

try:
    from helpers import FIXTURES
except ImportError:  # pragma: no cover
    from tests.helpers import FIXTURES

HAVE_FIXTURES = os.path.isdir(FIXTURES)


def fixture(name, fn):
    return os.path.join(FIXTURES, name, fn)


def have(name, fn="checklist.pdf"):
    return os.path.exists(fixture(name, fn))


@unittest.skipUnless(HAVE_FIXTURES, "fixtures/ not present")
class FixtureBuildTest(unittest.TestCase):
    _built = {}

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="tc-fixtures-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def build(self, name):
        if not have(name):
            self.skipTest("fixture %s missing" % name)
        if name not in self._built:
            from pipeline.build import build_set
            self._built[name] = build_set(os.path.join(FIXTURES, name), os.path.join(self.tmp, "data"),
                                          os.path.join(self.tmp, "reports"))
        return self._built[name][0]

    def sec(self, data, raw):
        return [s for s in data["sections"] if s["rawName"] == raw][0]

    def players(self, data):
        return [p for s in data["sections"] for c in s["cards"] for p in c["players"]]

    def test_all_fixtures_build(self):
        for name in sorted(os.listdir(FIXTURES)):
            if name.startswith(("_", ".")) or not have(name):
                continue
            data = self.build(name)
            self.assertGreater(data["stats"]["sections"], 0, name)
            self.assertGreater(data["stats"]["cards"], 0, name)
            for s in data["sections"]:
                self.assertIn(s["kind"], ("base", "variation", "insert", "autograph", "relic", "autograph-relic"))

    def test_inline_rookie_column(self):
        d = self.build("chrome-2025-bb")
        base = self.sec(d, "BASE CARDS")
        c3 = [c for c in base["cards"] if c["code"] == "3"][0]
        self.assertEqual(c3["players"][0]["name"], "Brooks Baldwin")
        self.assertEqual(c3["players"][0]["team"], "Chicago White Sox")
        self.assertTrue(c3["rookie"])
        self.assertFalse([c for c in base["cards"] if c["code"] == "1"][0]["rookie"])

    def test_mixed_alignment_codes(self):
        d = self.build("chrome-2024-bb")
        base = self.sec(d, "BASE CARDS")
        self.assertEqual(base["cards"][0]["code"], "1")
        self.assertEqual(base["cards"][0]["players"][0]["name"], "Shohei Ohtani")
        self.assertEqual(self.sec(d, "HELIX")["cards"][0]["code"], "HX-1")

    def test_glued_codes(self):
        d = self.build("topps-fb-2026")
        base = d["sections"][0]
        self.assertEqual(base["cards"][0]["code"], "1")
        self.assertEqual(base["cards"][0]["players"][0]["name"], "Marvin Harrison Jr.")
        self.assertEqual(base["cards"][9]["code"], "10")
        triple = self.sec(d, "NFL STARS TRIPLE AUTOGRAPHS")
        self.assertTrue(all(len(c["players"]) == 3 for c in triple["cards"]))

    def test_merged_code_cells_and_notes(self):
        d = self.build("mls")
        dual = self.sec(d, "CHROME DUAL AUTOGRAPHS")
        self.assertTrue(all(len(c["players"]) == 2 and c["code"] for c in dual["cards"]))
        rhythm = self.sec(d, "RHYTHM OF THE GAME")
        self.assertEqual(rhythm["cards"][0]["code"], "RG-1")
        self.assertTrue(any("hobby" in n.lower() for n in rhythm["notes"]))

    def test_group_is_section(self):
        d = self.build("resurgence-fb")
        self.assertEqual(d["sections"][0]["rawName"], "BASE")
        self.assertEqual(d["sections"][0]["cardCount"], 100)
        self.assertEqual(d["unmatchedOdds"], [])
        prism = [p for p in d["sections"][0]["parallels"] if p["id"] == "prism"][0]
        mega = [f["id"] for f in d["formats"]].index("mega")
        self.assertEqual(prism["odds"]["mega"]["raw"], "0.05")
        self.assertIsNone(prism["odds"]["mega"]["n"])
        self.assertEqual([f["label"] for f in d["formats"]], ["Hobby", "Delight", "Value", "Mega"])
        self.assertGreaterEqual(mega, 0)

    def test_jennie(self):
        d = self.build("jennie")
        self.assertEqual(d["name"], "2026 Topps Chrome x Jennie")
        self.assertEqual(len(d["formats"]), 1)
        self.assertEqual(d["unmatchedOdds"], [])
        base = self.sec(d, "BASE")
        self.assertIn("refractor", [p["id"] for p in base["parallels"]])
        kinds = dict((s["rawName"], s["kind"]) for s in d["sections"])
        self.assertEqual(kinds["CHROMIUM CLOSE-UPS INSERT"], "insert")
        self.assertEqual(kinds["CONCERT AUTOGRAPH-RELICS"], "autograph-relic")

    def test_inception(self):
        d = self.build("inception-bball")
        self.assertEqual(d["unmatchedOdds"], [])
        self.assertEqual([f["label"] for f in d["formats"]], ["Hobby", "FDI"])


@unittest.skipUnless(HAVE_FIXTURES and have("chrome-updates-bball", "odds.pdf"), "fixture odds missing")
class FixtureOddsOnlyTest(unittest.TestCase):
    def test_many_formats(self):
        from pipeline.odds import parse_odds
        r = parse_odds(fixture("chrome-updates-bball", "odds.pdf"))
        self.assertEqual(r["title"], "2025-26 Topps Chrome Updates Basketball")
        self.assertEqual(len(r["formats"]), 12)
        self.assertEqual(r["formats"][4]["label"], "Value Box EA")
        self.assertGreater(len(r["rows"]), 300)
        self.assertEqual(r["rows"][0]["name"], "Base")


if __name__ == "__main__":
    unittest.main()
