import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import yaml

try:
    from helpers import CHECKLIST_2026, FIXTURES, ODDS_2026
except ImportError:  # pragma: no cover
    from tests.helpers import CHECKLIST_2026, FIXTURES, ODDS_2026

from pipeline.__main__ import main


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(argv)
    return code, out.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tc-cli-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_new_then_build(self):
        sets = os.path.join(self.tmp, "sets")
        code, out = run(["new", "my-set", "--checklist", CHECKLIST_2026, "--odds", ODDS_2026, "--sets-dir", sets])
        self.assertEqual(code, 0, out)
        with open(os.path.join(sets, "my-set", "set.yaml")) as fh:
            cfg = yaml.safe_load(fh)
        self.assertEqual(cfg["name"], "2026 Topps Chrome Baseball")
        self.assertEqual(cfg["year"], 2026)
        self.assertEqual(cfg["sport"], "Baseball")
        self.assertEqual(cfg["primaryFormat"], "hobby")
        self.assertIn("breaker-delight", cfg["formats"])
        # odds-only folder is skipped, set without config builds with defaults
        os.makedirs(os.path.join(sets, "_ignored"))
        os.makedirs(os.path.join(sets, "odds-only"))
        shutil.copy(ODDS_2026, os.path.join(sets, "odds-only", "odds.pdf"))
        out_dir = os.path.join(self.tmp, "data")
        code, out = run(["build", "--sets-dir", sets, "--out-dir", out_dir, "--reports-dir", os.path.join(self.tmp, "r")])
        self.assertEqual(code, 0, out)
        self.assertIn("[odds-only] skipped", out)
        self.assertIn("349 matched / 0 unmatched", out)
        with open(os.path.join(out_dir, "sets.json")) as fh:
            index = json.load(fh)
        self.assertEqual([s["slug"] for s in index["sets"]], ["my-set"])
        with open(os.path.join(out_dir, "my-set.json")) as fh:
            first = json.load(fh)
        # rebuilding unchanged input keeps generatedAt (quiet diffs)
        code, out = run(["build", "my-set", "--sets-dir", sets, "--out-dir", out_dir, "--reports-dir", os.path.join(self.tmp, "r")])
        with open(os.path.join(out_dir, "my-set.json")) as fh:
            second = json.load(fh)
        self.assertEqual(first["generatedAt"], second["generatedAt"])

    def test_bad_pdf_fails(self):
        sets = os.path.join(self.tmp, "sets")
        os.makedirs(os.path.join(sets, "broken"))
        with open(os.path.join(sets, "broken", "checklist.pdf"), "w") as fh:
            fh.write("not a pdf")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, out = run(["build", "--sets-dir", sets, "--out-dir", os.path.join(self.tmp, "d"),
                             "--reports-dir", os.path.join(self.tmp, "r")])
        self.assertEqual(code, 1)
        self.assertIn("FAILED", err.getvalue())

    def test_inspect(self):
        code, out = run(["inspect", ODDS_2026])
        self.assertEqual(code, 0)
        self.assertIn("breaker-delight", out)
        code, out = run(["inspect", CHECKLIST_2026])
        self.assertEqual(code, 0)
        self.assertIn("page kinds", out)
        self.assertIn("ROOKIE AUTOGRAPHS", out)

    def test_images(self):
        sets = os.path.join(self.tmp, "sets")
        sd = os.path.join(sets, "img-set")
        os.makedirs(os.path.join(sd, "images"))
        shutil.copy(CHECKLIST_2026, os.path.join(sd, "checklist.pdf"))
        shutil.copy(ODDS_2026, os.path.join(sd, "odds.pdf"))
        for fn in ("base-cards--gold-refractor.jpg", "superfractor.png", "helix.webp", "x.jpg"):
            with open(os.path.join(sd, "images", fn), "wb") as fh:
                fh.write(b"img")
        with open(os.path.join(sd, "set.yaml"), "w") as fh:
            fh.write('name: Img Set\nimages:\n  "base-cards/red-refractor": x.jpg\n'
                     'overrides:\n  sections:\n    helix: { category: inserts, name: "Helix!" }\n'
                     '    minions-mlb: { hidden: true }\n')
        from pipeline.build import build_set
        data, report, summary = build_set(sd, os.path.join(self.tmp, "data"), os.path.join(self.tmp, "r"))
        secs = dict((s["id"], s) for s in data["sections"])
        base = dict((p["id"], p) for p in secs["base-cards"]["parallels"])
        self.assertEqual(base["gold-refractor"]["image"], "data/img-set/images/base-cards--gold-refractor.jpg")
        self.assertEqual(base["red-refractor"]["image"], "data/img-set/images/x.jpg")
        self.assertEqual(base["superfractor"]["image"], "data/img-set/images/superfractor.png")
        self.assertIsNone(base["refractor"]["image"])
        self.assertEqual(secs["helix"]["image"], "data/img-set/images/helix.webp")
        self.assertEqual(secs["helix"]["category"], "inserts")
        self.assertEqual(secs["helix"]["name"], "Helix!")
        self.assertNotIn("minions-mlb", secs)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "data", "img-set", "images", "superfractor.png")))


if __name__ == "__main__":
    unittest.main()
