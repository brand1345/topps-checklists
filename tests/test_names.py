import unittest

from pipeline.names import clean_name, clean_team, name_type_words, norm_token, slugify, smart_title, unique_id


class NamesTest(unittest.TestCase):
    def test_smart_title(self):
        self.assertEqual(smart_title("BASE CARDS GOLD RAYWAVE REFRACTOR"), "Base Cards Gold RayWave Refractor")
        self.assertEqual(smart_title("2025 MLB COMMISSIONERS TROPHY"), "2025 MLB Commissioners Trophy")
        self.assertEqual(smart_title("CLASS OF 2026 COOPERSTOWN CALLS"), "Class of 2026 Cooperstown Calls")
        self.assertEqual(smart_title("75TH DIAMOND AUTOGRAPHS"), "75th Diamond Autographs")
        self.assertEqual(smart_title("X-FRACTOR"), "X-Fractor")
        self.assertEqual(smart_title("TIE-DYE GEOMETRIC REFRACTOR"), "Tie-Dye Geometric Refractor")
        self.assertEqual(smart_title("RED WHITE AND BLUE REFRACTOR"), "Red White and Blue Refractor")
        self.assertEqual(smart_title("2025 MLB COMMISSIONER’S TROPHY"), "2025 MLB Commissioner's Trophy")
        # mixed case input is kept
        self.assertEqual(smart_title("Base Refractors Prism"), "Base Refractors Prism")
        # Topps' lower-case "x" collaborations; accented capitals are letters
        self.assertEqual(smart_title("TOPPS X SESAME STREET"), "Topps x Sesame Street")
        self.assertEqual(smart_title("X-FRACTOR"), "X-Fractor")
        self.assertEqual(smart_title("TOPPS CHROME EXPOS\u00c9"), "Topps Chrome Expos\u00e9")
        self.assertEqual(smart_title("BELTR\u00c9 GOLD"), "Beltr\u00e9 Gold")

    def test_slugify(self):
        self.assertEqual(slugify("BASE CARDS"), "base-cards")
        self.assertEqual(slugify("Gold RayWave Refractor"), "gold-raywave-refractor")
        self.assertEqual(slugify("Adrián Beltré"), "adrian-beltre")
        self.assertEqual(slugify("COMMISSIONER'S"), "commissioners")
        used = set()
        self.assertEqual(unique_id("a", used), "a")
        self.assertEqual(unique_id("a", used), "a-2")

    def test_team(self):
        self.assertEqual(clean_team("Los Angeles Dodgers®"), "Los Angeles Dodgers")
        self.assertEqual(clean_team("Milwaukee Brewers™ "), "Milwaukee Brewers")
        self.assertEqual(clean_team("Baltimore Oroles®"), "Baltimore Oroles")  # source typo kept
        self.assertEqual(clean_name("World Series Champions\u2122"), "World Series Champions")

    def test_tokens(self):
        self.assertEqual(norm_token("ROOKIES"), "ROOKIE")
        self.assertEqual(norm_token("TOPPS"), "TOPPS")
        self.assertEqual(norm_token("SERIES"), "SERIES")
        self.assertEqual(norm_token("AUTOS"), "AUTOGRAPH")
        self.assertEqual(norm_token("COMMISSIONER’S"), "COMMISSIONER")
        self.assertEqual(norm_token("EXPOS\u00c9"), "EXPOSE")
        self.assertEqual(norm_token("PATCHES"), "PATCH")

    def test_type_words(self):
        self.assertEqual(name_type_words("CONCERT SIGNATURES"), (True, False))
        self.assertEqual(name_type_words("CONCERT SIGNATURES", strict=True), (False, False))
        self.assertEqual(name_type_words("ROOKIE PATCH AUTOGRAPHS"), (True, True))
        self.assertEqual(name_type_words("NBA DEBUT PATCH (NON-AUTOGRAPH)"), (False, True))


if __name__ == "__main__":
    unittest.main()
