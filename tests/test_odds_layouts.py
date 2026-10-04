"""Odds sheet layout variants on small synthetic PDFs."""
import shutil
import unittest

try:
    import synthpdf as sp
except ImportError:  # pragma: no cover
    from tests import synthpdf as sp

from pipeline.odds import format_label, parse_odds, parse_value

W, H = 1224, 792


def rows(r):
    return [(row["rawName"], row["values"]) for row in r["rows"]]


class OddsLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = sp.TempDir()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp.path, ignore_errors=True)

    def parse(self, name, pages):
        return parse_odds(sp.write(self.tmp.file(name), pages, width=W, height=H))

    def test_baseline(self):
        r = self.parse("ok.pdf", [sp.odds_page(sp.ODDS_BODY), sp.odds_page(sp.ODDS_BODY)])
        self.assertEqual([f["id"] for f in r["formats"]], ["hobby", "jumbo", "mega", "blaster"])
        self.assertEqual(len(r["rows"]), 8)
        self.assertEqual(r["warnings"], [])

    def test_unterminated_disclaimer_does_not_swallow_rows(self):
        r = self.parse("disc.pdf", [sp.odds_page(sp.ODDS_BODY, disclaimer_end="may differ"),
                                    sp.odds_page(sp.ODDS_BODY)])
        self.assertEqual(len(r["rows"]), 8)
        self.assertEqual(rows(r)[0], ("BASE CARDS REFRACTOR", ["1:3", "1:1", "1:4", "-"]))
        self.assertTrue(any("Disclaimer" in w for w in r["warnings"]))

    def test_footer_is_not_part_of_a_name(self):
        page = sp.odds_page(sp.ODDS_BODY, extra=[(14, 740, "Odds are subject to change. Page 1", "R")])
        r = self.parse("foot.pdf", [page])
        self.assertEqual(rows(r)[-1][0], "HELIX SUPERFRACTOR")
        self.assertTrue(any("Ignored odds line" in w for w in r["warnings"]))

    def test_na_only_row_is_a_row(self):
        body = sp.ODDS_BODY + [("HELIX SAPPHIRE", ["N/A", "N/A", "-", "-"]), ("ULTRAVIOLET", ["1:200", "-", "-", "-"])]
        r = self.parse("na.pdf", [sp.odds_page(body)])
        self.assertEqual([n for n, _ in rows(r)][-2:], ["HELIX SAPPHIRE", "ULTRAVIOLET"])
        self.assertTrue(all(v is None for v in r["rows"][-2]["odds"].values()))

    def test_wrapped_name_with_centred_values(self):
        it = sp.odds_page(sp.ODDS_BODY[:2])
        it += [(14, 97, "TOPPS CHROME ROOKIE AUTOGRAPHS GREEN", "R")]
        it += sp.odds_row(102.5, None, ["1:500", "1:900", "-", "-"])
        it += [(14, 108, "GEOMETRIC REFRACTOR", "R")]
        it += sp.odds_row(122, "HELIX", ["1:1,000", "-", "-", "-"])
        r = self.parse("vc.pdf", [it])
        self.assertEqual([n for n, _ in rows(r)], ["BASE CARDS REFRACTOR", "BASE CARDS GOLD REFRACTOR",
                                                   "TOPPS CHROME ROOKIE AUTOGRAPHS GREEN GEOMETRIC REFRACTOR", "HELIX"])

    def test_wrapped_name_below_row(self):
        it = sp.odds_page(sp.ODDS_BODY[:2])
        it += sp.odds_row(97, "TOPPS CHROME ROOKIE AUTOGRAPHS GREEN", ["1:500", "1:900", "-", "-"])
        it += [(14, 106, "GEOMETRIC REFRACTOR", "R")]
        it += sp.odds_row(119, "HELIX", ["1:1,000", "-", "-", "-"])
        r = self.parse("wrap.pdf", [it])
        self.assertEqual(rows(r)[2][0], "TOPPS CHROME ROOKIE AUTOGRAPHS GREEN GEOMETRIC REFRACTOR")

    def test_centred_dashes_do_not_create_columns(self):
        r = self.parse("dash.pdf", [sp.odds_page(sp.ODDS_BODY * 3, dash_x=40)])
        self.assertEqual([f["id"] for f in r["formats"]], ["hobby", "jumbo", "mega", "blaster"])
        self.assertEqual(rows(r)[0][1], ["1:3", "1:1", "1:4", "-"])

    def test_dash_only_column_with_label(self):
        body = [(n, v[:3] + ["-"]) for n, v in sp.ODDS_BODY] * 2
        r = self.parse("dashcol.pdf", [sp.odds_page(body)])
        self.assertEqual([f["id"] for f in r["formats"]], ["hobby", "jumbo", "mega", "blaster"])
        self.assertTrue(all(row["odds"]["blaster"] is None for row in r["rows"]))

    def test_curly_apostrophe_kept_in_raw_name(self):
        body = [("2025 MLB COMMISSIONER’S TROPHY", ["1:2,848,800", "-", "-", "-"])] + sp.ODDS_BODY
        r = self.parse("apos.pdf", [sp.odds_page(body)])
        self.assertEqual(r["rows"][0]["rawName"], "2025 MLB COMMISSIONER’S TROPHY")
        self.assertEqual(r["rows"][0]["name"], "2025 MLB COMMISSIONER'S TROPHY")


class OddsValueRegressionTest(unittest.TestCase):
    def test_plain_thousands(self):
        self.assertEqual(parse_value("1:6818"), {"raw": "1:6818", "n": 6818})
        self.assertEqual(parse_value("1:448000"), {"raw": "1:448000", "n": 448000})
        self.assertEqual(parse_value("N/A"), None)
        self.assertEqual(parse_value("1:1,2175")["error"], "malformed number in source")

    def test_format_label_product_names(self):
        self.assertEqual(format_label("6625 - NBA CHROME 2025-26 HOBBY"), ("HOBBY", "6625"))
        self.assertEqual(format_label("7001 - TOPPS SERIES 1 2027 HOBBY"), ("HOBBY", "7001"))
        self.assertEqual(format_label("6625 - MLB-CHROME HOBBY"), ("HOBBY", "6625"))
        self.assertEqual(format_label("1234 - HOBBY"), ("HOBBY", "1234"))


if __name__ == "__main__":
    unittest.main()
