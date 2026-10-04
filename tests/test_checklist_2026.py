"""Checklist parsing of the real 2026 Topps Chrome Baseball PDF (committed in sets/)."""
import re
import unittest

import pdfplumber

try:
    from helpers import CHECKLIST_2026, parsed_checklist_2026
except ImportError:  # pragma: no cover
    from tests.helpers import CHECKLIST_2026, parsed_checklist_2026


def _independent_counts():
    """Count card rows and Rookie words straight from the PDF with a deliberately simple method:
    a card row is a line of regular-weight (non-bold, non-italic), on-page words."""
    rows = 0
    rookie_words = 0
    with pdfplumber.open(CHECKLIST_2026) as pdf:
        for page in pdf.pages:
            words = page.extract_words(extra_attrs=["fontname"])
            lines = {}
            for w in words:
                if w["x0"] < 0:
                    continue
                lines.setdefault(round(w["top"]), []).append(w)
            for ws in lines.values():
                fonts = set(w["fontname"] for w in ws)
                if any("Bold" in f or "Italic" in f for f in fonts):
                    continue
                texts = [w["text"] for w in ws]
                if texts == ["Rookie"]:
                    rookie_words += 1
                    continue
                rows += 1
    return rows, rookie_words


class Checklist2026Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cl = parsed_checklist_2026()
        cls.secs = dict((s["rawName"], s) for s in cls.cl["sections"])

    def players(self):
        for s in self.cl["sections"]:
            for c in s["cards"]:
                for p in c["players"]:
                    yield s, c, p

    def test_title_and_disclaimer(self):
        self.assertEqual(self.cl["title"], "2026 Topps Chrome Baseball")
        self.assertTrue(self.cl["disclaimer"].startswith("Checklists provided by Topps"))
        self.assertTrue(self.cl["disclaimer"].endswith("may vary."))

    def test_every_row_exactly_once(self):
        rows, _ = _independent_counts()
        self.assertEqual(rows, 1643)
        self.assertEqual(sum(1 for _ in self.players()), rows)
        self.assertEqual(sum(s["rowCount"] for s in self.cl["sections"]), rows)

    def test_rookie_flags_all_mapped(self):
        _, rookie_words = _independent_counts()
        self.assertEqual(rookie_words, 412)
        self.assertEqual(self.cl["stats"]["rookieFlagsOverflow"], rookie_words)
        self.assertEqual(self.cl["stats"]["rookieFlagsOverflowMapped"], rookie_words)
        self.assertEqual(sum(1 for _, _, p in self.players() if p["rookie"]), rookie_words)
        self.assertFalse([w for w in self.cl["warnings"] if "Rookie" in w])

    def test_overflow_pages(self):
        d = self.cl["debug"]
        self.assertEqual(d["pageKinds"], "M" * 32 + "O" * 31)
        self.assertEqual(d["overflowMap"][33], 1)
        self.assertEqual(d["overflowMap"][63], 31)

    def test_base_spot_checks(self):
        base = self.secs["BASE CARDS"]
        self.assertEqual(base["group"], "BASE")
        self.assertEqual(len(base["cards"]), 300)
        by_code = dict((c["code"], c) for c in base["cards"])
        self.assertEqual(by_code["1"]["players"][0]["name"], "Shohei Ohtani")
        self.assertEqual(by_code["1"]["players"][0]["team"], "Los Angeles Dodgers")
        self.assertFalse(by_code["1"]["rookie"])
        self.assertEqual(by_code["6"]["players"][0]["name"], "Sal Stewart")
        self.assertTrue(by_code["6"]["rookie"])
        self.assertEqual(by_code["7"]["players"][0]["name"], "Samuel Basallo")
        self.assertTrue(by_code["7"]["rookie"])

    def test_sections_and_groups(self):
        names = [s["rawName"] for s in self.cl["sections"]]
        self.assertEqual(len(names), 55)
        self.assertEqual(names[0], "BASE CARDS")
        self.assertEqual(names[-1], "BACK TO BACK DUAL GOLD LOGOMAN AUTOGRAPH RELICS")
        self.assertEqual(self.secs["HELIX"]["group"], "INSERT")
        self.assertEqual(self.secs["INK STROKES"]["group"], "AUTOGRAPH")
        self.assertEqual(self.secs["GOLD LOGOMAN RELICS"]["group"], "RELIC")
        self.assertEqual(self.secs["GOLD LOGOMAN AUTOGRAPH RELICS"]["group"], "AUTOGRAPH RELIC")
        for g in ("BASE", "INSERT", "AUTOGRAPH", "RELIC", "AUTOGRAPH RELIC"):
            self.assertNotIn(g, names[1:] if g == "BASE" else names)

    def test_multi_player_cards(self):
        ptp = self.secs["PAST TO PRESENT"]
        self.assertEqual(len(ptp["cards"]), 25)
        first = ptp["cards"][0]
        self.assertEqual(first["code"], "PTP-1")
        self.assertEqual([p["name"] for p in first["players"]], ["Mickey Mantle", "Aaron Judge"])
        dual = self.secs["DUAL AUTOGRAPHS"]
        self.assertTrue(all(len(c["players"]) == 2 for c in dual["cards"]))
        self.assertIn("DA-SD", [c["code"] for c in dual["cards"]])
        for name in ("GOLD LOGOMAN DUAL RELICS", "GOLD LOGOMAN DUAL AUTOGRAPH RELICS"):
            self.assertEqual([len(c["players"]) for c in self.secs[name]["cards"]], [2, 2, 2])

    def test_rows_without_code_or_name(self):
        fan = self.secs["FANATICS AUTHENTICS REDEMPTION CARDS"]
        self.assertEqual(len(fan["cards"]), 30)
        self.assertTrue(all(c["code"] == "" and len(c["players"]) == 1 for c in fan["cards"]))
        self.assertEqual(fan["cards"][0]["players"][0]["name"], "Chase Utley")
        ct = self.secs["2025 MLB COMMISSIONERS TROPHY"]["cards"]
        self.assertEqual(len(ct), 1)
        self.assertEqual(ct[0]["code"], "CT-1")
        self.assertEqual(ct[0]["players"][0]["name"], "")
        self.assertEqual(ct[0]["players"][0]["team"], "Los Angeles Dodgers")

    def test_same_code_in_two_sections(self):
        a = self.secs["CLASS OF 2026 COOPERSTOWN CALLS"]["cards"]
        b = self.secs["CLASS OF 2025 COOPERSTOWN CALLS"]["cards"]
        self.assertEqual(a[0]["code"], "CC-1")
        self.assertEqual(b[0]["code"], "CC-1")
        self.assertNotEqual(a[0]["players"][0]["name"], b[0]["players"][0]["name"])

    def test_source_typos_preserved(self):
        names = set(p["name"] for _, _, p in self.players())
        teams = set(p["team"] for _, _, p in self.players())
        self.assertIn("Oniel Cruz", names)
        self.assertIn("Baltimore Oroles", teams)

    def test_no_marks_in_teams(self):
        for _, _, p in self.players():
            self.assertFalse(re.search(u"[®™]", p["team"]), p)

    def test_no_warnings(self):
        self.assertEqual(self.cl["warnings"], [])

    def test_blank_overflow_page_left_out(self):
        """Excel exports may drop blank overflow pages: page 53 (the empty Rookie page of main
        page 21) removed must not shift the Rookie flags of every later page."""
        import os
        import shutil
        import tempfile
        try:
            import pypdfium2
        except ImportError:  # pragma: no cover
            self.skipTest("pypdfium2 not installed")
        from pipeline.checklist import parse_checklist
        tmp = tempfile.mkdtemp(prefix="tc-omit-")
        try:
            doc = pypdfium2.PdfDocument(CHECKLIST_2026)
            doc.del_page(52)
            path = os.path.join(tmp, "checklist.pdf")
            doc.save(path)
            doc.close()
            r = parse_checklist(path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        flags = lambda cl: [(s["rawName"], c["code"], p["name"], p["rookie"])
                            for s in cl["sections"] for c in s["cards"] for p in c["players"]]
        self.assertEqual(flags(r), flags(self.cl))
        self.assertEqual(r["stats"]["rookieFlagsOverflowMapped"], 412)
        self.assertTrue(any("not page order" in w for w in r["warnings"]))


if __name__ == "__main__":
    unittest.main()
