import unittest

from pipeline import classify


class KindTest(unittest.TestCase):
    def test_groups(self):
        k = classify.section_kind
        self.assertEqual(k("BASE CARDS", "BASE"), "base")
        self.assertEqual(k("HELIX", "INSERT"), "insert")
        self.assertEqual(k("BASE CARDS IMAGE VARIATIONS", "INSERT"), "variation")
        self.assertEqual(k("SUPER SHORT PRINTS", "INSERT"), "variation")
        self.assertEqual(k("AWARD WINNERS BASE VARIATION", "INSERT"), "variation")
        self.assertEqual(k("ROOKIE AUTOGRAPHS", "AUTOGRAPH"), "autograph")
        self.assertEqual(k("GOLD LOGOMAN RELICS", "RELIC"), "relic")
        self.assertEqual(k("GOLD LOGOMAN AUTOGRAPH RELICS", "AUTOGRAPH RELIC"), "autograph-relic")
        self.assertEqual(k("X AUTOGRAPH PATCH", "RELIC"), "autograph-relic")
        self.assertEqual(k("NBA DEBUT PATCH (NON-AUTOGRAPH)", "RELIC"), "relic")
        self.assertEqual(k("MLS DEBUT PATCH AUTOGRAPHS", "AUTOGRAPH-RELIC"), "autograph-relic")
        # everything under BASE (Jennie-style checklists): the name decides
        self.assertEqual(k("CHROMIUM CLOSE-UPS INSERT", "BASE"), "insert")
        self.assertEqual(k("CONCERT AUTOGRAPH-RELICS", "BASE"), "autograph-relic")
        self.assertEqual(k("RUBY SHORT PRINTS", "BASE"), "variation")
        self.assertEqual(k("ROOKIES", "BASE"), "base")
        # other autograph / relic words when the group doesn't say
        self.assertEqual(k("CONCERT SIGNATURES", "BASE"), "autograph")
        self.assertEqual(k("ROOKIE PATCH CARDS", "BASE"), "relic")
        self.assertEqual(k("NFL MATERIAL CARDS", "BASE"), "relic")
        self.assertEqual(k("FIELD FIT SWATCH COLLECTION", ""), "relic")
        self.assertEqual(k("ROOKIE PATCH AUTOGRAPHS", ""), "autograph-relic")
        self.assertEqual(k("BILLBOARD MATERIAL", "INSERT"), "insert")
        self.assertEqual(k("NBA DEBUT PATCH (NON-AUTOGRAPH)", "BASE"), "relic")

    def test_category(self):
        c = classify.category_for
        self.assertEqual(c("variation", "ultra"), "base")
        self.assertEqual(c("insert", "case-hit"), "case-hits")
        self.assertEqual(c("insert", "ultra"), "case-hits")
        self.assertEqual(c("insert", "short-print"), "inserts")
        self.assertEqual(c("insert", None), "inserts")
        self.assertEqual(c("autograph", "common"), "autographs")
        self.assertEqual(c("autograph-relic", "ultra"), "relics")


class RuleHelpersTest(unittest.TestCase):
    def test_year_free_key(self):
        self.assertEqual(classify.year_free_key("CLASS OF 2026 COOPERSTOWN CALLS"),
                         classify.year_free_key("CLASS OF 2025 COOPERSTOWN CALLS"))
        self.assertNotEqual(classify.year_free_key("1991 TOPPS BASEBALL"), classify.year_free_key("TOPPS BASEBALL CARDS"))

    def test_is_base_variation(self):
        base = {"17": {("Juan Soto",)}, "100": {("Aaron Judge",)}}
        card = lambda code, *names: {"code": code, "players": [{"name": n} for n in names]}
        self.assertTrue(classify.is_base_variation([card("17", "Juan Soto"), card("100", "Aaron Judge")], base))
        self.assertFalse(classify.is_base_variation([card("17", "Juan Soto"), card("100", "Someone Else")], base))
        self.assertFalse(classify.is_base_variation([card("MVP-1", "Juan Soto")], base))
        self.assertFalse(classify.is_base_variation([], base))

    def test_basis_source_error(self):
        sec = {"odds": None, "parallels": [{"odds": {"hobby": {"raw": "1:1,2175", "n": 12175, "error": "x"}}},
                                           {"odds": {"hobby": {"raw": "1:569,760", "n": 569760}}}]}
        self.assertEqual(classify.basis_source_error(sec, {"format": "hobby", "n": 12175})["raw"], "1:1,2175")
        self.assertIsNone(classify.basis_source_error(sec, {"format": "hobby", "n": 569760}))


class TierTest(unittest.TestCase):
    def setUp(self):
        self.formats = [
            {"id": "hobby", "packsPerBox": 20, "boxesPerCase": 12},
            {"id": "mega", "packsPerBox": None, "boxesPerCase": None},
        ]

    def sec(self, base=None, parallels=()):
        return {"odds": base, "parallels": [{"odds": p} for p in parallels]}

    def test_thresholds(self):
        for n, tier in [(20, "common"), (21, "short-print"), (240, "short-print"), (241, "case-hit"),
                        (2400, "case-hit"), (2401, "ultra")]:
            t, basis = classify.compute_tier(self.sec({"hobby": {"raw": "", "n": n}, "mega": None}),
                                             self.formats, "hobby")
            self.assertEqual(t, tier, n)
        self.assertEqual(basis["perBox"], 0.00833)   # 4 significant figures for small rates

    def test_rate_rounding_keeps_tiny_values(self):
        self.assertEqual(classify.round_rate(20 / 3.0), 6.6667)
        self.assertEqual(classify.round_rate(20 / 2848800.0), 7.02e-06)
        self.assertEqual(classify.round_rate(240 / 316534.0), 0.0007582)
        self.assertEqual(classify.round_rate(240.0), 240.0)
        t, basis = classify.compute_tier(self.sec({"hobby": {"raw": "", "n": 2848800}}), self.formats, "hobby")
        self.assertGreater(basis["perBox"], 0)

    def test_parallel_fallback_and_other_format(self):
        t, basis = classify.compute_tier(self.sec(None, [{"hobby": {"n": 3}}, {"hobby": {"n": 500}}]),
                                         self.formats, "hobby")
        self.assertEqual((t, basis["n"]), ("common", 3))
        t, basis = classify.compute_tier(self.sec({"hobby": None, "mega": {"n": 1175}}), self.formats, "hobby")
        self.assertEqual((t, basis["format"], basis["perBox"]), ("case-hit", "mega", None))
        self.assertEqual(classify.compute_tier(self.sec(None), self.formats, "hobby"), (None, None))

    def test_overrides(self):
        t, _ = classify.compute_tier(self.sec({"hobby": {"n": 100}}), self.formats, "hobby", {"commonMax": 100})
        self.assertEqual(t, "common")


if __name__ == "__main__":
    unittest.main()
