import unittest

from pipeline.odds import format_label, parse_value


class OddsValueTest(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(parse_value("1:341"), {"raw": "1:341", "n": 341})
        self.assertEqual(parse_value("1:1,705"), {"raw": "1:1,705", "n": 1705})
        self.assertEqual(parse_value("1:2,848,800")["n"], 2848800)

    def test_not_available(self):
        self.assertIsNone(parse_value("-"))
        self.assertIsNone(parse_value(""))

    def test_source_errors_preserved(self):
        v = parse_value("1:1,2175")
        self.assertEqual(v["raw"], "1:1,2175")
        self.assertEqual(v["n"], 12175)
        self.assertEqual(v["error"], "malformed number in source")
        v = parse_value("0.39374999999999999")
        self.assertEqual(v["raw"], "0.39374999999999999")
        self.assertIsNone(v["n"])
        self.assertEqual(v["error"], "unreadable value in source")
        self.assertIsNone(parse_value("0.05")["n"])

    def test_format_labels(self):
        self.assertEqual(format_label("6625 - MLB-CHROME 2026 HOBBY"), ("HOBBY", "6625"))
        self.assertEqual(format_label("6623 - MLB-CHROME 2026 BREAKER DELIGHT"), ("BREAKER DELIGHT", "6623"))
        self.assertEqual(format_label("Hobby Pack Rate"), ("Hobby", None))
        self.assertEqual(format_label("Odds (Per Pack)"), ("Per Pack", None))
        self.assertEqual(format_label("Value Box EA"), ("Value Box EA", None))


if __name__ == "__main__":
    unittest.main()
