"""Checklist layout variants on small synthetic PDFs (run in CI; no real PDFs needed)."""
import shutil
import unittest

try:
    import synthpdf as sp
except ImportError:  # pragma: no cover
    from tests import synthpdf as sp

from pipeline.checklist import ChecklistError, map_overflow, parse_checklist


def cards(r, raw=None):
    secs = r["sections"] if raw is None else [s for s in r["sections"] if s["rawName"] == raw]
    return [c for s in secs for c in s["cards"]]


class LayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = sp.TempDir()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp.path, ignore_errors=True)

    def parse(self, name, pages, **kw):
        return parse_checklist(sp.write(self.tmp.file(name), pages, **kw))

    # ---------------------------------------------------------------- columns

    def test_long_name_not_split_mid_word(self):
        long_name = "Emmanuel Henderson Jr. Junior"
        self.assertTrue(205 < 100 + sp.text_width(long_name) < 258)   # crosses the gutter midpoint
        items = sp.title() + [(40, 56, "BASE", "B"), (40, 68, "BASE CARDS", "B")] + sp.rows("", 30, 80, codefmt="%s%d")
        items += [(40, 80 + 30 * 12, "392", "R"), (100, 80 + 30 * 12, long_name, "R"),
                  (260, 80 + 30 * 12, "Seattle Seahawks\xae", "R")]
        r = self.parse("longname.pdf", [items])
        c = [c for c in cards(r) if c["code"] == "392"][0]
        self.assertEqual((c["players"][0]["name"], c["players"][0]["team"]), (long_name, "Seattle Seahawks"))

    def test_name_drawn_under_team_text(self):
        # the name overflows under the team cell; content-stream order keeps both intact
        long_name = "Christian Encarnacion-Strand Junior The Third"
        self.assertGreater(100 + sp.text_width(long_name), 265)
        items = sp.title() + [(40, 56, "BASE", "B"), (40, 68, "BASE CARDS", "B")] + sp.rows("", 30, 80, codefmt="%s%d")
        t = 80 + 30 * 12
        items += [(40, t, "65", "R"), (100, t, long_name, "R"), (260, t, "Cincinnati Reds\xae", "R")]
        r = self.parse("overlap.pdf", [items])
        c = [c for c in cards(r) if c["code"] == "65"][0]
        self.assertEqual(c["players"][0]["name"], long_name)
        self.assertEqual(c["players"][0]["team"], "Cincinnati Reds")

    def test_one_overflowing_cell_keeps_team_gutter(self):
        items = sp.title() + [(40, 56, "BASE", "B"), (40, 68, "BASE CARDS", "B")] + sp.rows("", 60, 80, codefmt="%s%d")
        page2 = [(40, 40, "INSERT", "B"), (40, 52, "COMMISSIONERS TROPHY", "B"), (40, 64, "CT-1", "R"),
                 (100, 64, "Los Angeles Dodgers 2026 World Series Champions Trophy Card", "R")]
        r = self.parse("spill.pdf", [items, page2])
        self.assertTrue(r["debug"]["roles"]["team"])
        first = cards(r, "BASE CARDS")[0]["players"][0]
        self.assertEqual((first["name"], first["team"]), ("Player Name1", "New York Yankees"))

    def test_flag_column_tags(self):
        extra = {3: "Rookie", 6: "Future Stars", 9: "League Leaders", 12: "RC", 15: "Rookie Card",
                 18: "Combo Card"}.get
        items = sp.title() + [(40, 56, "BASE", "B"), (40, 68, "BASE CARDS", "B")] + sp.rows("", 30, 80, codefmt="%s%d", extra=extra)
        r = self.parse("col4.pdf", [items])
        by = dict((c["code"], c) for c in cards(r))
        self.assertEqual([k for k in sorted(by, key=int) if by[k]["rookie"]], ["3", "12", "15"])
        self.assertEqual(by["6"]["tags"], ["Future Stars"])
        self.assertEqual(by["18"]["tags"], ["Combo Card"])
        self.assertNotIn("tags", by["3"])
        for c in by.values():
            self.assertIn(c["players"][0]["team"], [t.rstrip("\xae") for t in sp.TEAMS])

    # ---------------------------------------------------------------- merged / continuation codes

    def test_wrapped_name_with_centred_code_and_team(self):
        items = sp.title() + [(40, 56, "AUTOGRAPH", "B"), (40, 68, "DUAL AUTOGRAPHS", "B")]
        t = 80
        for i in range(1, 9):
            if i == 4:
                items += [(100, t, "Christopher Alexander", "R"), (40, t + 6, "DA-4", "R"),
                          (260, t + 6, sp.TEAMS[0], "R"), (100, t + 12, "Montgomery-Smith Jr.", "R")]
                t += 24
            else:
                items += [(40, t, "DA-%d" % i, "R"), (100, t, "Player Name%d" % i, "R"), (260, t, sp.TEAMS[i % 4], "R")]
                t += 12
        r = self.parse("wrap.pdf", [items])
        cs = cards(r)
        self.assertEqual(len(cs), 8)
        da4 = [c for c in cs if c["code"] == "DA-4"][0]
        self.assertEqual([(p["name"], p["team"]) for p in da4["players"]],
                         [("Christopher Alexander Montgomery-Smith Jr.", "Los Angeles Dodgers")])

    def test_dual_cards_with_centred_code_keep_code_line_text(self):
        # base rows set the usual row pitch (13pt); each dual card is two rows 6.5pt off its code
        items = sp.title() + [(40, 56, "BASE", "B"), (40, 68, "BASE CARDS", "B")] + \
            sp.rows("", 30, 80, codefmt="%s%d", pitch=13)
        items += [(40, 480, "AUTOGRAPH", "B"), (40, 493, "NATIONAL PAIRINGS DUAL AUTOGRAPHS", "B")]
        t = 506
        for i, country in enumerate(["Argentina", "USA", "Canada"]):
            items += [(100, t, "First Player%d" % i, "R"), (260, t, "Club A%d" % i, "R"),
                      (40, t + 6.5, "NPDA-%d" % i, "R"), (420, t + 6.5, country, "R"),
                      (100, t + 13, "Second Player%d" % i, "R"), (260, t + 13, "Club B%d" % i, "R")]
            t += 26
        r = self.parse("pairs.pdf", [items])
        cs = cards(r, "NATIONAL PAIRINGS DUAL AUTOGRAPHS")
        self.assertEqual([len(c["players"]) for c in cs[:3]], [2, 2, 2])
        self.assertEqual([c.get("tags") for c in cs[:3]], [["Argentina"], ["USA"], ["Canada"]])
        self.assertEqual(cs[0]["players"][1]["team"], "Club B0")

    def test_single_coded_row_does_not_swallow_section(self):
        items = sp.title() + [(40, 56, "INSERT", "B"), (40, 68, "FANATICS AUTHENTICS", "B"),
                              (40, 80, "FA-1", "R"), (100, 80, "Player One", "R"), (260, 80, sp.TEAMS[0], "R")]
        for i in range(2, 31):
            items += [(100, 68 + i * 12, "Player Number%d" % i, "R"), (260, 68 + i * 12, sp.TEAMS[i % 4], "R")]
        r = self.parse("fa.pdf", [items])
        cs = cards(r)
        self.assertEqual(len(cs), 30)
        self.assertTrue(all(len(c["players"]) == 1 for c in cs))

    def test_same_player_twice_is_two_cards(self):
        items = sp.title() + [(40, 56, "INSERT", "B"), (40, 68, "IMAGE VARIATIONS", "B")]
        items += [(40, 80, "1", "R"), (100, 80, "Shohei Ohtani", "R"), (260, 80, sp.TEAMS[0], "R"),
                  (40, 92, "1", "R"), (100, 92, "Shohei Ohtani", "R"), (260, 92, sp.TEAMS[0], "R"),
                  (40, 104, "2", "R"), (100, 104, "Aaron Judge", "R"), (260, 104, sp.TEAMS[1], "R")]
        r = self.parse("dupe.pdf", [items])
        self.assertEqual([len(c["players"]) for c in cards(r)], [1, 1, 1])
        self.assertTrue(any("twice in a row" in w for w in r["warnings"]))

    def test_trademark_glyph_stripped_from_names(self):
        items = sp.title() + [(40, 56, "INSERT", "B"), (40, 68, "CHAMPION REFRACTORS", "B"),
                              (40, 80, "CHAMP-16", "R"), (100, 80, "World Series Champions\u2122", "R"),
                              (260, 80, sp.TEAMS[0], "R")] + sp.rows("CHAMP", 3, 92)
        r = self.parse("tm.pdf", [items])
        self.assertEqual(cards(r)[0]["players"][0]["name"], "World Series Champions")

    # ---------------------------------------------------------------- headers / page furniture

    def test_repeated_column_header_and_footer(self):
        for font in ("B", "R"):
            hdr = [(40, 30, "Card #", font), (100, 30, "Player", font), (260, 30, "Team", font), (420, 30, "Rookie", font)]
            p1 = sp.title(10) + hdr + [(40, 56, "BASE", "B"), (40, 68, "BASE CARDS", "B")] + \
                sp.rows("", 40, 80, codefmt="%s%d", rookie=lambda i: i % 5 == 0) + [(280, 760, "Page 1 of 2", "R")]
            body2 = [(x, t, str(int(s) + 40) if (x == 40 and s.isdigit()) else s, f)
                     for (x, t, s, f) in sp.rows("", 20, 50, codefmt="%s%d", rookie=lambda i: i % 5 == 0)]
            p2 = hdr + body2 + [(40, 300, "INSERT", "B"), (40, 312, "HELIX", "B")] + sp.rows("HX", 10, 324) + \
                [(280, 760, "Page 2 of 2", "R")]
            r = self.parse("hdr%s.pdf" % font, [p1, p2])
            got = [(s["rawName"], len(s["cards"]), sum(1 for c in s["cards"] if c["rookie"])) for s in r["sections"]]
            self.assertEqual(got, [("BASE CARDS", 60, 12), ("HELIX", 10, 0)], font)

    def test_repeated_group_and_section_headers_continue_section(self):
        def body(offset):
            return [(x, t, str(int(s) + offset) if x == 40 else s, f)
                    for (x, t, s, f) in sp.rows("", 20, 80, codefmt="%s%d")]
        p1 = sp.title() + [(40, 56, "BASE", "B"), (40, 68, "BASE CARDS", "B")] + body(0)
        p2 = [(40, 56, "BASE", "B"), (40, 68, "BASE CARDS", "B")] + body(20)
        p3 = [(40, 68, "BASE CARDS (CONTINUED)", "B")] + body(40)
        r = self.parse("rep.pdf", [p1, p2, p3])
        self.assertEqual([(s["rawName"], len(s["cards"])) for s in r["sections"]], [("BASE CARDS", 60)])

    def test_empty_section_header_keeps_group(self):
        from pipeline.classify import section_kind
        items = sp.title() + [(40, 56, "BASE", "B"), (40, 68, "BASE CARDS", "B")] + sp.rows("", 10, 80, codefmt="%s%d")
        items += [(40, 210, "AUTOGRAPH", "B"), (40, 222, "SUPERFRACTOR AUTOGRAPH VARIATIONS", "B"),
                  (40, 234, "INK STROKES", "B")] + sp.rows("IS", 5, 246) + [(40, 320, "CHROMOGRAPHS", "B")] + sp.rows("CG", 5, 332)
        r = self.parse("empty.pdf", [items])
        secs = dict((s["rawName"], s) for s in r["sections"])
        self.assertEqual(secs["INK STROKES"]["group"], "AUTOGRAPH")
        self.assertEqual(secs["CHROMOGRAPHS"]["group"], "AUTOGRAPH")
        self.assertEqual(section_kind("CHROMOGRAPHS", secs["CHROMOGRAPHS"]["group"]), "autograph")
        self.assertEqual(secs["SUPERFRACTOR AUTOGRAPH VARIATIONS"]["cards"], [])
        self.assertIn("No cards listed in the checklist", secs["SUPERFRACTOR AUTOGRAPH VARIATIONS"]["notes"])

    def test_headers_without_bold_font(self):
        items = [(40, 40, "BASE", "R"), (40, 52, "BASE CARDS", "R")] + sp.rows("", 10, 64, codefmt="%s%d") + \
            [(40, 196, "INSERT", "R"), (40, 208, "HELIX", "R")] + sp.rows("HX", 5, 220)
        r = self.parse("nobold.pdf", [items])
        self.assertEqual([(s["rawName"], len(s["cards"])) for s in r["sections"]], [("BASE CARDS", 10), ("HELIX", 5)])
        self.assertTrue(any("No bold header lines" in w for w in r["warnings"]))

    def test_no_text_is_an_error(self):
        with self.assertRaises(ChecklistError):
            self.parse("blank.pdf", [[]])

    # ---------------------------------------------------------------- Rookie overflow pages

    def _main_pages(self):
        p1 = sp.title() + [(40, 56, "BASE", "B"), (40, 68, "BASE CARDS", "B")] + sp.rows("", 10, 80, codefmt="%s%d")
        p2 = [(40, 68, "HELIX", "B")] + sp.rows("HX", 10, 80)
        p3 = [(40, 68, "ULTRAVIOLET", "B")] + sp.rows("UV", 10, 80)
        return p1, p2, p3

    def rc(self, r):
        return dict((s["rawName"], sum(1 for c in s["cards"] if c["rookie"])) for s in r["sections"])

    def test_interleaved_overflow_pages(self):
        p1, p2, p3 = self._main_pages()
        r = self.parse("inter.pdf", [p1, sp.flag_page([1, 2]), p2, sp.flag_page([3]), p3, sp.flag_page([4, 5])])
        self.assertEqual(r["debug"]["pageKinds"], "MOMOMO")
        self.assertEqual(self.rc(r), {"BASE CARDS": 2, "HELIX": 1, "ULTRAVIOLET": 2})

    def test_non_flag_word_on_overflow_page(self):
        p1, p2, p3 = self._main_pages()
        fl = sp.flag_page([1, 2]) + [(40, 80 + 2 * 12, "Future Stars", "R")]
        r = self.parse("trail_other.pdf", [p1, p2, p3, fl, sp.flag_page([3]), sp.flag_page([4, 5])])
        self.assertEqual(r["debug"]["pageKinds"], "MMMOOO")
        self.assertEqual(self.rc(r), {"BASE CARDS": 2, "HELIX": 1, "ULTRAVIOLET": 2})
        self.assertEqual(cards(r, "BASE CARDS")[2].get("tags"), ["Future Stars"])
        self.assertEqual(sum(len(s["cards"]) for s in r["sections"]), 30)

    def test_trailing_overflow_aligned_by_rows_not_page_order(self):
        # page 2 has its rows lower down than pages 1 and 3; the blank overflow page for page 2
        # was left out, so page order would send the last overflow page to page 2.
        p1, _p2, p3 = self._main_pages()
        p2 = [(40, 68, "HELIX", "B")] + sp.rows("HX", 4, 80) + [(40, 140, "WILD STYLE", "B")] + sp.rows("WS", 4, 158, pitch=15)
        r = self.parse("trail_omit.pdf", [p1, p2, p3, sp.flag_page([1, 2]), sp.flag_page([9, 10])])
        self.assertEqual(r["debug"]["overflowMap"], {4: 1, 5: 3})
        self.assertEqual(self.rc(r)["ULTRAVIOLET"], 2)
        self.assertEqual(self.rc(r)["WILD STYLE"], 0)
        self.assertTrue(any("not page order" in w for w in r["warnings"]))


class MapOverflowTest(unittest.TestCase):
    """map_overflow on page-kind strings with fake rows."""

    class L(object):
        def __init__(self, top, kind="flag"):
            self.top = top
            self.kind = kind

    def pages(self, kinds, flags=None):
        out = []
        for i, k in enumerate(kinds):
            lines = [self.L(t) for t in (flags or {}).get(i, [])] if k == "O" else []
            out.append({"index": i, "kind": k, "lines": lines})
        return out

    def test_patterns(self):
        rows = dict((i, [self.L(80 + 12 * j, "row") for j in range(10)]) for i in range(6))
        w = []
        self.assertEqual(map_overflow(self.pages("MOMOMO", {1: [80], 3: [92], 5: [104]}), rows, w), {1: 0, 3: 2, 5: 4})
        self.assertEqual(map_overflow(self.pages("MMMOOO", {3: [80], 4: [80], 5: [80]}), rows, w), {3: 0, 4: 1, 5: 2})
        # rows of page 2 are not at y=80 -> the second overflow page belongs to page 3
        rows[1] = [self.L(300 + 12 * j, "row") for j in range(10)]
        self.assertEqual(map_overflow(self.pages("MMMOO", {3: [80], 4: [80]}), rows, w), {3: 0, 4: 2})


if __name__ == "__main__":
    unittest.main()
