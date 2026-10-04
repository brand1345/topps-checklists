"""Matcher tests on the 2026 Topps Chrome section list (no PDF needed)."""
import unittest

from pipeline.classify import section_kind
from pipeline.match import Matcher, parallel_display

SECTIONS_2026 = [
    ("BASE", "BASE CARDS"), ("INSERT", "ULTRAVIOLET"), ("INSERT", "BASE CARDS LIGHTBOARD LOGO VARIATION"),
    ("INSERT", "2025 CHROME MVP BUYBACKS"), ("INSERT", "NUMBERS LIVE FOREVER"),
    ("INSERT", "CLASS OF 2026 COOPERSTOWN CALLS"), ("INSERT", "CLASS OF 2025 COOPERSTOWN CALLS"),
    ("INSERT", "AWARD WINNERS BASE VARIATION"), ("INSERT", "TOPPS CHROME RADIATING ROOKIES"),
    ("INSERT", "FUTURE STARS"), ("INSERT", "SUPER SHORT PRINTS"), ("INSERT", "PERSPECTIVES"),
    ("INSERT", "WORLD SERIES AT NIGHT"), ("INSERT", "TOPPS CHROME CHAMPION REFRACTORS"),
    ("INSERT", "SHADOW ETCH"), ("INSERT", "HELIX"), ("INSERT", "STATIC NOISE"), ("INSERT", "HOBBY MASTERS"),
    ("INSERT", "FANATICAL"), ("INSERT", "WILD STYLE"), ("INSERT", "PAST TO PRESENT"),
    ("INSERT", "TOPPS CHROME EXPOSE"), ("INSERT", "BASE CARDS IMAGE VARIATIONS"),
    ("INSERT", "BIG TICKET PLAYERS"), ("INSERT", "WRECKING CREW"), ("INSERT", "1991 TOPPS BASEBALL"),
    ("INSERT", "DIAMOND MOMENTS"), ("INSERT", "2025 MLB COMMISSIONERS TROPHY"),
    ("INSERT", "CHROME RIVALS HOME"), ("INSERT", "CHROME RIVALS AWAY"),
    ("INSERT", "FANATICS AUTHENTICS REDEMPTION CARDS"), ("INSERT", "MINIONS MLB"),
    ("AUTOGRAPH", "ROOKIE AUTOGRAPHS"), ("AUTOGRAPH", "RETAIL ROOKIE AUTOGRAPHS"),
    ("AUTOGRAPH", "CHROME AUTOGRAPHS"), ("AUTOGRAPH", "CHROME LEGEND AUTOGRAPHS"),
    ("AUTOGRAPH", "WORLD SERIES CHAMPIONS AUTOGRAPHS"), ("AUTOGRAPH", "1991 TOPPS BASEBALL AUTOGRAPHS"),
    ("AUTOGRAPH", "FUTURE STARS AUTOGRAPHS"), ("AUTOGRAPH", "PERSPECTIVES AUTOGRAPHS"),
    ("AUTOGRAPH", "INK STROKES"), ("AUTOGRAPH", "75TH DIAMOND AUTOGRAPHS"), ("AUTOGRAPH", "CHROMOGRAPHS"),
    ("AUTOGRAPH", "2025 WORLD CHAMPIONS AUTOGRAPH REFRACTOR"),
    ("AUTOGRAPH", "TOPPS CHROME RADIATING ROOKIES AUTOGRAPHS"), ("AUTOGRAPH", "DUAL AUTOGRAPHS"),
    ("AUTOGRAPH", "2025 CHROME MVP BUYBACKS AUTOGRAPHS"), ("AUTOGRAPH", "COOPERSTOWN CALLS AUTOGRAPH VARIATION"),
    ("AUTOGRAPH", "NUMBERS LIVE FOREVER AUTOGRAPH VARIATION"), ("AUTOGRAPH", "TOPPS AUTOGRAPH CARD JERRY SEINFELD"),
    ("RELIC", "GOLD LOGOMAN RELICS"), ("RELIC", "GOLD LOGOMAN DUAL RELICS"),
    ("AUTOGRAPH RELIC", "GOLD LOGOMAN DUAL AUTOGRAPH RELICS"), ("AUTOGRAPH RELIC", "GOLD LOGOMAN AUTOGRAPH RELICS"),
    ("AUTOGRAPH RELIC", "BACK TO BACK DUAL GOLD LOGOMAN AUTOGRAPH RELICS"),
]

# (odds row, expected section raw name, expected parallel tail ('' = base version))
SPEC_TABLE = [
    ("BASE CARDS REFRACTOR", "BASE CARDS", "REFRACTOR"),
    ("BASE CARDS TOPPS 75TH ANNIVERSARY", "BASE CARDS", "TOPPS 75TH ANNIVERSARY"),
    ("BASE CARDS TOPPS REFRACTOR", "BASE CARDS", "TOPPS REFRACTOR"),
    ("BASE CARDS IMAGE VARIATIONS GOLD REFRACTOR", "BASE CARDS IMAGE VARIATIONS", "GOLD REFRACTOR"),
    ("BASE CARDS IMAGE VARIATIONS", "BASE CARDS IMAGE VARIATIONS", ""),
    ("BASE CARDS SUPER SHORT PRINTS", "SUPER SHORT PRINTS", ""),
    ("BASE CARDS LIGHTBOARD LOGO VARIATION", "BASE CARDS LIGHTBOARD LOGO VARIATION", ""),
    ("CHROME RADIATING ROOKIES", "TOPPS CHROME RADIATING ROOKIES", ""),
    ("MVP BUYBACKS PRISM", "2025 CHROME MVP BUYBACKS", "PRISM"),
    ("TOPPS CHROME CHAMPION GOLD", "TOPPS CHROME CHAMPION REFRACTORS", "GOLD"),
    ("TOPPS CHROME CHAMPION GOLD SUPERFRACTOR", "TOPPS CHROME CHAMPION REFRACTORS", "GOLD SUPERFRACTOR"),
    ("TOPPS CHROME ROOKIE AUTOGRAPHS TEAL REFRACTOR", "ROOKIE AUTOGRAPHS", "TEAL REFRACTOR"),
    ("TOPPS CHROME ROOKIE AUTOGRAPHS", "ROOKIE AUTOGRAPHS", ""),
    ("TOPPS CHROME RETAIL ROOKIE AUTOGRAPHS GOLD RAYWAVE REFRACTOR", "RETAIL ROOKIE AUTOGRAPHS", "GOLD RAYWAVE REFRACTOR"),
    ("TOPPS CHROME LEGENDS AUTOGRAPHS RED REFRACTOR", "CHROME LEGEND AUTOGRAPHS", "RED REFRACTOR"),
    ("1991 TOPPS CHROME AUTOGRAPHS ORANGE", "1991 TOPPS BASEBALL AUTOGRAPHS", "ORANGE"),
    ("1991 TOPPS BASEBALL GREEN", "1991 TOPPS BASEBALL", "GREEN"),
    ("2025 WORLD SERIES CHAMPIONS AUTOGRAPHS GOLD REFRACTOR", "2025 WORLD CHAMPIONS AUTOGRAPH REFRACTOR", "GOLD REFRACTOR"),
    ("WORLD SERIES CHAMPIONS AUTOGRAPHS SUPERFRACTOR", "WORLD SERIES CHAMPIONS AUTOGRAPHS", "SUPERFRACTOR"),
    ("WORLD SERIES AT NIGHT", "WORLD SERIES AT NIGHT", ""),
    ("CLASS OF 2026 COOPERSTOWN CALLS AUTOGRAPH VARIATION BLACK", "COOPERSTOWN CALLS AUTOGRAPH VARIATION", "BLACK"),
    ("CLASS OF 2025 COOPERSTOWN CALLS GREEN REFRACTOR", "CLASS OF 2025 COOPERSTOWN CALLS", "GREEN REFRACTOR"),
    ("TOPPS CHROME MVP BUYBACKS AUTOGRAPHS", "2025 CHROME MVP BUYBACKS AUTOGRAPHS", ""),
    ("TOPPS CHROME RADIATING ROOKIES AUTOGRAPHS SUPERFRACTOR", "TOPPS CHROME RADIATING ROOKIES AUTOGRAPHS", "SUPERFRACTOR"),
    ("2025 MLB COMMISSIONER’S TROPHY", "2025 MLB COMMISSIONERS TROPHY", ""),
    ("GOLD LOGOMAN RELICS REDEMPTION CARD", "GOLD LOGOMAN RELICS", ""),
    ("GOLD LOGOMAN DUAL RELICS REDEMPTION CARD", "GOLD LOGOMAN DUAL RELICS", ""),
    ("GOLD LOGOMAN DUAL AUTOGRAPH RELICS REDEMPTION CARD", "GOLD LOGOMAN DUAL AUTOGRAPH RELICS", ""),
    ("75TH DIAMOND AUTOGRAPHS PRINTING PLATES", "75TH DIAMOND AUTOGRAPHS", "PRINTING PLATES"),
    ("FANATICS AUTHENTICS REDEMPTION CARDS", "FANATICS AUTHENTICS REDEMPTION CARDS", ""),
    ("CHROME RIVALS HOME GREEN", "CHROME RIVALS HOME", "GREEN"),
    ("CHROME RIVALS AWAY SUPERFRACTOR", "CHROME RIVALS AWAY", "SUPERFRACTOR"),
    ("TOPPS AUTOGRAPH CARD JERRY SEINFELD BLACK REFRACTOR", "TOPPS AUTOGRAPH CARD JERRY SEINFELD", "BLACK REFRACTOR"),
    ("NUMBERS LIVE FOREVER AUTOGRAPH VARIATION SUPERFRACTOR", "NUMBERS LIVE FOREVER AUTOGRAPH VARIATION", "SUPERFRACTOR"),
    ("NUMBERS LIVE FOREVER GOLD", "NUMBERS LIVE FOREVER", "GOLD"),
]


def sections():
    return [{"rawName": raw, "kind": section_kind(raw, grp)} for grp, raw in SECTIONS_2026]


class MatchTest(unittest.TestCase):
    def setUp(self):
        self.secs = sections()
        self.m = Matcher(self.secs)

    def test_spec_table(self):
        for odds, sec, tail in SPEC_TABLE:
            r = self.m.match(odds)
            self.assertIsNotNone(r["section"], odds)
            self.assertEqual(self.secs[r["section"]]["rawName"], sec, odds)
            self.assertEqual(r["tail"].upper(), tail, odds)

    def test_redemption_flag(self):
        self.assertTrue(self.m.match("GOLD LOGOMAN RELICS REDEMPTION CARD")["redemption"])
        self.assertFalse(self.m.match("HELIX SUPERFRACTOR")["redemption"])

    def test_how(self):
        self.assertEqual(self.m.match("HELIX")["how"], "exact")
        self.assertEqual(self.m.match("BASE CARDS GOLD REFRACTOR")["how"], "exact")
        self.assertEqual(self.m.match("MVP BUYBACKS PRISM")["how"], "heuristic")

    def test_alias(self):
        m = Matcher(self.secs, {"TOPPS CHROME LEGENDS AUTOGRAPHS": "CHROME LEGEND AUTOGRAPHS"})
        r = m.match("TOPPS CHROME LEGENDS AUTOGRAPHS GOLD REFRACTOR")
        self.assertEqual(r["how"], "alias")
        self.assertEqual(self.secs[r["section"]]["rawName"], "CHROME LEGEND AUTOGRAPHS")
        self.assertEqual(r["tail"], "GOLD REFRACTOR")

    def test_unmatched(self):
        r = self.m.match("SOMETHING COMPLETELY DIFFERENT")
        self.assertIsNone(r["section"])
        self.assertTrue(r["reason"])

    def test_title_case_and_parallel_suffix(self):
        m = Matcher([{"rawName": "BASE", "kind": "base"}, {"rawName": "ROOKIES", "kind": "base"},
                     {"rawName": "CHROMIUM CLOSE-UPS INSERT", "kind": "insert"}])
        r = m.match("Base Refractors Prism")
        self.assertEqual(r["section"], 0)
        self.assertEqual(r["tail"], "Refractors Prism")
        r = m.match("BASE CARDS REFRACTOR")
        self.assertEqual((r["section"], r["tail"]), (0, "REFRACTOR"))
        r = m.match("Rookies Base")
        self.assertEqual((r["section"], r["tail"]), (1, ""))
        r = m.match("CHROMIUM CLOSE-UPS AQUA")
        self.assertEqual((r["section"], r["tail"]), (2, "AQUA"))


# topps-fb-2026 (Flagship-style "BASE CARDS I" plus a year-prefixed insert)
SECTIONS_FB = [
    ("BASE", "BASE CARDS I"), ("BASE", "FUTURE STARS"), ("BASE", "ROOKIES"),
    ("INSERT", "BILLBOARD MATERIAL"), ("INSERT", "1991 TOPPS FOOTBALL"),
    ("INSERT", "1991 TOPPS FOOTBALL CHROME BASE CARDS"), ("RELIC", "ROOKIE PATCH RELICS"),
    ("AUTOGRAPH", "ROOKIE AUTOGRAPHS"),
]


def sections_of(lst):
    return [{"rawName": raw, "kind": section_kind(raw, grp)} for grp, raw in lst]


class MatchRegressionTest(unittest.TestCase):
    def test_base_parallels_not_sent_to_year_prefixed_insert(self):
        secs = sections_of(SECTIONS_FB)
        m = Matcher(secs)
        for odds, sec, tail in [("BASE CARDS GOLD", "BASE CARDS I", "GOLD"),
                                ("BASE GOLD FOIL", "BASE CARDS I", "GOLD FOIL"),
                                ("1991 TOPPS FOOTBALL CHROME BASE CARDS REFRACTOR",
                                 "1991 TOPPS FOOTBALL CHROME BASE CARDS", "REFRACTOR"),
                                ("1991 TOPPS FOOTBALL GOLD", "1991 TOPPS FOOTBALL", "GOLD"),
                                ("BILLBOARD MATERIAL GOLD", "BILLBOARD MATERIAL", "GOLD")]:
            r = m.match(odds)
            self.assertEqual((secs[r["section"]]["rawName"], r["tail"].upper()), (sec, tail), odds)

    def test_plain_row_prefers_insert_and_compounds_match(self):
        secs = sections_of([("INSERT", "ULTRA VIOLET ALL STARS"),
                            ("AUTOGRAPH", "TOPPS CHROME ULTRAVIOLET ALL STARS AUTOGRAPHS")])
        m = Matcher(secs)
        for odds, idx, tail in [("ULTRAVIOLET ALL STARS", 0, ""), ("ULTRA VIOLET ALL STARS GOLD", 0, "GOLD"),
                                ("ULTRAVIOLET ALL STARS GOLD", 0, "GOLD"),
                                ("ULTRA VIOLET ALL STARS AUTOGRAPHS RED", 1, "RED"),
                                ("TOPPS CHROME ULTRAVIOLET ALL STARS AUTOGRAPHS", 1, "")]:
            r = m.match(odds)
            self.assertEqual((r["section"], r["tail"].upper()), (idx, tail), odds)

    def test_accents(self):
        m = Matcher([{"rawName": "TOPPS CHROME EXPOS\u00c9", "kind": "insert"}, {"rawName": "HELIX", "kind": "insert"}])
        r = m.match("TOPPS CHROME EXPOSE GOLD")
        self.assertEqual((r["section"], r["tail"]), (0, "GOLD"))
        self.assertEqual(m.match("TOPPS CHROME EXPOS\u00c9")["how"], "exact")

    def test_unused_alias_reported(self):
        m = Matcher(sections(), {"TOPPS CHROME LEGENDS AUTOGRAPH": "CHROME LEGEND AUTOGRAPHS",
                                 "NOTHING HERE": "NO SUCH SECTION"})
        m.match("TOPPS CHROME LEGENDS AUTOGRAPHS RED REFRACTOR")
        self.assertIn("TOPPS CHROME LEGENDS AUTOGRAPH", m.unused_aliases())
        self.assertEqual(m.alias_target_missing(), ["NOTHING HERE"])

    def test_parallel_display_canonical_spelling(self):
        self.assertEqual(parallel_display("SuperFractor"), "Superfractor")
        self.assertEqual(parallel_display("Base SuperFractors"), "Base Superfractors")
        self.assertEqual(parallel_display("GOLD RAYWAVE REFRACTOR"), "Gold RayWave Refractor")


if __name__ == "__main__":
    unittest.main()
