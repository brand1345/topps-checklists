"""End-to-end build of the real set: JSON contract + odds accounting."""
import json
import os
import unittest

try:
    from helpers import ROOT, built_2026, built_2026_live, parsed_odds_2026
except ImportError:  # pragma: no cover
    from tests.helpers import ROOT, built_2026, built_2026_live, parsed_odds_2026

EXPECTED_CATEGORY = {
    "ultraviolet": "case-hits", "helix": "case-hits", "hobby-masters": "case-hits",
    "shadow-etch": "case-hits", "topps-chrome-radiating-rookies": "case-hits",
    "world-series-at-night": "case-hits", "topps-chrome-expose": "case-hits",
    "numbers-live-forever": "case-hits",
    "1991-topps-baseball": "inserts", "future-stars": "inserts", "perspectives": "inserts",
    "big-ticket-players": "inserts", "wrecking-crew": "inserts",
    "base-cards": "base", "base-cards-image-variations": "base", "super-short-prints": "base",
    "base-cards-lightboard-logo-variation": "base", "award-winners-base-variation": "base",
    "minions-mlb": "base", "class-of-2026-cooperstown-calls": "case-hits",
    "class-of-2025-cooperstown-calls": "case-hits",
    "rookie-autographs": "autographs", "ink-strokes": "autographs",
    "gold-logoman-relics": "relics", "gold-logoman-autograph-relics": "relics",
}


class Build2026Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.report, cls.summary, cls.tmp = built_2026()
        cls.secs = dict((s["id"], s) for s in cls.data["sections"])

    def test_top_level_contract(self):
        d = self.data
        for key in ("schemaVersion", "slug", "name", "year", "sport", "brand", "generatedAt", "disclaimer",
                    "formats", "categories", "sections", "unmatchedOdds", "warnings", "stats"):
            self.assertIn(key, d)
        self.assertEqual(d["schemaVersion"], 1)
        self.assertEqual(d["slug"], "2026-topps-chrome-baseball")
        self.assertEqual(d["name"], "2026 Topps Chrome Baseball")
        self.assertEqual((d["year"], d["sport"], d["brand"]), (2026, "Baseball", "Topps"))
        self.assertEqual([c["id"] for c in d["categories"]], ["base", "inserts", "case-hits", "autographs", "relics"])
        self.assertEqual(sum(c["sectionCount"] for c in d["categories"]), len(d["sections"]))
        json.dumps(d)  # serialisable

    def test_formats(self):
        f = self.data["formats"]
        self.assertEqual([x["id"] for x in f], ["hobby", "jumbo", "value-box", "mega", "breaker-delight", "fanatics"])
        self.assertEqual(f[0]["raw"], "6625 - MLB-CHROME 2026 HOBBY")
        self.assertEqual(f[0]["code"], "6625")
        self.assertTrue(f[0]["primary"])
        self.assertEqual((f[0]["packsPerBox"], f[0]["boxesPerCase"]), (20, 12))
        self.assertEqual(f[4]["label"], "Breaker's Delight")
        self.assertEqual(sum(1 for x in f if x["primary"]), 1)

    def test_every_odds_row_accounted(self):
        od = parsed_odds_2026()
        n_rows = len(od["rows"])
        self.assertEqual(self.data["stats"]["oddsRows"], n_rows)
        used = sum(len(s["parallels"]) + (1 if s["oddsName"] else 0) for s in self.data["sections"])
        self.assertEqual(used + len(self.data["unmatchedOdds"]), n_rows)
        self.assertEqual(self.data["unmatchedOdds"], [])
        raw_used = [s["oddsName"] for s in self.data["sections"] if s["oddsName"]] + \
            [p["rawName"] for s in self.data["sections"] for p in s["parallels"]]
        self.assertEqual(sorted(raw_used), sorted(r["rawName"] for r in od["rows"]))

    def test_wrapped_names_joined(self):
        ra = self.secs["rookie-autographs"]
        names = [p["name"] for p in ra["parallels"]]
        self.assertIn("Green Geometric Refractor", names)
        self.assertIn("Tie-Dye Geometric Refractor", names)
        rra = self.secs["retail-rookie-autographs"]
        self.assertIn("Orange RayWave Refractor", [p["name"] for p in rra["parallels"]])

    def test_source_errors_kept(self):
        sec = self.secs["2025-world-champions-autograph-refractor"]
        gold = [p for p in sec["parallels"] if p["id"] == "gold-refractor"][0]
        self.assertEqual(gold["odds"]["hobby"], {"raw": "1:1,2175", "n": 12175, "error": "malformed number in source"})
        self.assertEqual(gold["odds"]["breaker-delight"]["raw"], "0.39374999999999999")
        self.assertIsNone(gold["odds"]["breaker-delight"]["n"])

    def test_no_odds_parallels_kept(self):
        iv = self.secs["base-cards-image-variations"]
        sapph = [p for p in iv["parallels"] if p["id"] == "sapphire"][0]
        self.assertEqual(sapph["formats"], [])
        self.assertTrue(all(v is None for v in sapph["odds"].values()))
        self.assertIn("padpardascha", [p["id"] for p in iv["parallels"]])

    def test_section_shapes(self):
        for s in self.data["sections"]:
            for key in ("id", "name", "rawName", "group", "kind", "category", "tier", "tierBasis", "redemption",
                        "cardCount", "rookieCount", "cards", "odds", "oddsName", "parallels", "image", "notes"):
                self.assertIn(key, s)
            self.assertEqual(s["cardCount"], len(s["cards"]))
            self.assertEqual(s["rookieCount"], sum(1 for c in s["cards"] if c["rookie"]))
            pids = [p["id"] for p in s["parallels"]]
            self.assertEqual(len(pids), len(set(pids)), s["id"])
            for p in s["parallels"]:
                self.assertIn(p["match"], ("exact", "heuristic", "alias"))
                self.assertEqual(list(p["odds"].keys()), [f["id"] for f in self.data["formats"]])
        ids = [s["id"] for s in self.data["sections"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_categories(self):
        for sid, cat in EXPECTED_CATEGORY.items():
            self.assertEqual(self.secs[sid]["category"], cat, sid)

    def test_tiers(self):
        self.assertEqual(self.secs["base-cards"]["tier"], "common")
        self.assertEqual(self.secs["base-cards"]["tierBasis"], {"format": "hobby", "n": 3, "perBox": 6.6667, "perCase": 80.0})
        self.assertEqual(self.secs["static-noise"]["tierBasis"]["perBox"], 0.005106)   # mega: 6 packs/box
        self.assertEqual(self.secs["static-noise"]["tierBasis"]["format"], "mega")
        self.assertIsNone(self.secs["chrome-autographs"]["tier"])
        self.assertIn("No odds listed for this section", self.secs["chrome-autographs"]["notes"])

    def test_redemption(self):
        self.assertTrue(self.secs["gold-logoman-relics"]["redemption"])
        self.assertEqual(self.secs["gold-logoman-relics"]["oddsName"], "GOLD LOGOMAN RELICS REDEMPTION CARD")
        self.assertEqual(self.secs["gold-logoman-relics"]["parallels"], [])
        self.assertFalse(self.secs["helix"]["redemption"])

    def test_report(self):
        self.assertIn("## Odds rows", self.report)
        self.assertIn("| 1 | BASE CARDS REFRACTOR | BASE CARDS | Refractor | exact |", self.report)
        self.assertEqual(self.summary["unmatched"], 0)

    def test_box_configs(self):
        f = dict((x["id"], (x["packsPerBox"], x["boxesPerCase"])) for x in self.data["formats"])
        self.assertEqual(f, {"hobby": (20, 12), "jumbo": (12, 8), "value-box": (7, 40), "mega": (6, 20),
                             "breaker-delight": (1, 6), "fanatics": (6, 20)})

    def test_review_fixes(self):
        s = self.secs
        # odds row names are kept exactly as printed (curly apostrophe)
        self.assertEqual(s["2025-mlb-commissioners-trophy"]["oddsName"], u"2025 MLB COMMISSIONER\u2019S TROPHY")
        self.assertEqual(s["2025-mlb-commissioners-trophy"]["name"], "2025 MLB Commissioner's Trophy")
        self.assertEqual(s["2025-mlb-commissioners-trophy"]["rawName"], "2025 MLB COMMISSIONERS TROPHY")
        # tiny per-box rates keep significant figures
        self.assertEqual(s["2025-mlb-commissioners-trophy"]["tierBasis"]["perBox"], 7.02e-06)
        self.assertGreater(s["gold-logoman-dual-relics"]["tierBasis"]["perBox"], 0)
        # Minions MLB repeats base cards -> a base variation
        self.assertEqual(s["minions-mlb"]["kind"], "variation")
        # no-odds Class of 2026 follows Class of 2025
        self.assertTrue(any("Class of 2025" in n for n in s["class-of-2026-cooperstown-calls"]["notes"]))
        self.assertIn("Listed by Topps without odds in any format: Sapphire, Gold Sapphire, Orange Sapphire, "
                      "Black Sapphire, Red Sapphire, Padpardascha", s["base-cards-image-variations"]["notes"])
        self.assertTrue(any("1:1,2175" in n for n in s["2025-world-champions-autograph-refractor"]["notes"]))
        champ = [c for c in s["topps-chrome-champion-refractors"]["cards"] if c["code"] == "CHAMP-16"][0]
        self.assertEqual(champ["players"][0]["name"], "World Series Champions")

    @unittest.skipIf(os.environ.get("CI"), "CI rebuilds site/data right after the tests")
    def test_committed_site_data_is_current(self):
        """site/data must exist for the frontend (rebuilt with `python -m pipeline build`)."""
        path = os.path.join(ROOT, "site", "data", "2026-topps-chrome-baseball.json")
        if not os.path.exists(path):
            self.skipTest("site/data not built yet")
        with open(path, encoding="utf-8") as fh:
            committed = json.load(fh)
        a = dict(committed)
        b = json.loads(json.dumps(built_2026_live()[0]))
        a.pop("generatedAt")
        b.pop("generatedAt")
        self.assertEqual(a, b, "site/data is stale: run `python -m pipeline build`")


if __name__ == "__main__":
    unittest.main()
