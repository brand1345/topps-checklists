"""set.yaml handling, CLI robustness and build-level rules on a small synthetic set."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import yaml

try:
    import synthpdf as sp
except ImportError:  # pragma: no cover
    from tests import synthpdf as sp

from pipeline.__main__ import main
from pipeline.build import (BuildError, build_set, detect_meta, find_pdfs, load_config, prune_outputs,
                            scaffold, scaffold_yaml, validate_config, write_index)

BASE_PLAYERS = ["Juan Soto", "Aaron Judge", "Paul Skenes", "Roman Anthony"]


def make_checklist(path):
    p1 = sp.title() + [(40, 56, "BASE", "B"), (40, 68, "BASE CARDS", "B")]
    t = 80
    for i in range(1, 21):
        name = BASE_PLAYERS[i - 1] if i <= 4 else "Player Name%d" % i
        p1 += [(40, t, str(i), "R"), (100, t, name, "R"), (260, t, sp.TEAMS[i % 4], "R")]
        t += 12
    p1 += [(40, t, "INSERT", "B"), (40, t + 12, "MINIONS MLB", "B")]
    t += 24
    for i in (1, 2, 3, 4):
        p1 += [(40, t, str(i), "R"), (100, t, BASE_PLAYERS[i - 1], "R"), (260, t, sp.TEAMS[i % 4], "R")]
        t += 12
    p1 += [(40, t, "CLASS OF 2026 COOPERSTOWN CALLS", "B")] + sp.rows("CC", 3, t + 12)
    t += 12 + 36
    p1 += [(40, t, "CLASS OF 2025 COOPERSTOWN CALLS", "B")] + sp.rows("CC", 3, t + 12)
    t += 12 + 36
    p1 += [(40, t, "HELIX", "B")] + sp.rows("HX", 3, t + 12)
    t += 12 + 36
    p1 += [(40, t, "AUTOGRAPH", "B"), (40, t + 12, "DRUSKI SPIKE LEE TOPPS CHROME AUTOGRAPHS", "B")]
    p1 += [(40, t + 24, "TCA-D", "R"), (100, t + 24, "Druski", "R"), (40, t + 36, "TCA-SL", "R"),
           (100, t + 36, "Spike Lee", "R")]
    return sp.write(path, [p1])


ODDS_ROWS = [
    ("BASE CARDS REFRACTOR", ["1:3", "1:1", "1:4", "-"]),
    ("BASE CARDS SAPPHIRE", ["-", "-", "-", "-"]),
    ("BASE CARDS SUPERFRACTORS", ["1:50,000", "-", "-", "-"]),
    ("MINIONS MLB", ["1:12,775", "-", "-", "-"]),
    ("CLASS OF 2025 COOPERSTOWN CALLS", ["1:11,350", "-", "-", "-"]),
    ("HELIX", ["1:1,000", "-", "-", "-"]),
    ("TOPPS CHROME AUTOGRAPHS DRUSKI REFRACTORS ORANGE", ["1:20,000", "-", "-", "-"]),
    ("TOPPS CHROME AUTOGRAPHS SPIKE LEE REFRACTORS ORANGE", ["1:20,000", "-", "-", "-"]),
    ("TOPPS CHROME AUTOGRAPHS DRUSKI REFRACTORS GOLD", ["1:9,000", "-", "-", "-"]),
]


def make_odds(path):
    return sp.write(path, [sp.odds_page(ODDS_ROWS)], width=1224, height=792)


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class SynthSetMixin(object):
    @classmethod
    def setUpClass(cls):
        cls.src = tempfile.mkdtemp(prefix="tc-src-")
        cls.checklist = make_checklist(os.path.join(cls.src, "checklist.pdf"))
        cls.odds = make_odds(os.path.join(cls.src, "odds.pdf"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.src, ignore_errors=True)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tc-cfg-")
        self.sets = os.path.join(self.tmp, "sets")
        self.out = os.path.join(self.tmp, "data")
        self.rep = os.path.join(self.tmp, "reports")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_set(self, slug="synth-set", yaml_text=None, odds=True):
        d = os.path.join(self.sets, slug)
        os.makedirs(d)
        shutil.copy(self.checklist, os.path.join(d, "checklist.pdf"))
        if odds:
            shutil.copy(self.odds, os.path.join(d, "odds.pdf"))
        if yaml_text is not None:
            with open(os.path.join(d, "set.yaml"), "w", encoding="utf-8") as fh:
                fh.write(yaml_text)
        return d

    def build(self, d):
        return build_set(d, self.out, self.rep, now="2026-01-01T00:00:00Z")


class BuildRulesTest(SynthSetMixin, unittest.TestCase):
    def test_rules(self):
        data, report, summary = self.build(self.make_set(yaml_text="name: Synth Set\n"))
        secs = dict((s["id"], s) for s in data["sections"])
        self.assertEqual(summary["unmatched"], 0)
        # base-numbered "insert" -> variation (Base & Parallels)
        self.assertEqual((secs["minions-mlb"]["kind"], secs["minions-mlb"]["category"]), ("variation", "base"))
        # no-odds insert follows its sibling from another year
        self.assertEqual(secs["class-of-2025-cooperstown-calls"]["category"], "case-hits")
        c26 = secs["class-of-2026-cooperstown-calls"]
        self.assertEqual((c26["tier"], c26["category"]), (None, "case-hits"))
        self.assertIn("No odds listed for this section", c26["notes"])
        self.assertTrue(any("Class of 2025 Cooperstown Calls" in n for n in c26["notes"]))
        # parallels without odds anywhere are explained
        self.assertIn("Listed by Topps without odds in any format: Sapphire", secs["base-cards"]["notes"])
        # same parallel name from two sub-subjects
        names = [p["name"] for p in secs["druski-spike-lee-topps-chrome-autographs"]["parallels"]]
        self.assertEqual(names, ["Druski Refractors Orange", "Spike Lee Refractors Orange", "Refractors Gold"])
        self.assertFalse([w for w in data["warnings"] if "Duplicate parallel" in w])
        self.assertIn("## Images", report)

    def test_images(self):
        d = self.make_set(yaml_text='name: Img\nimages:\n  "base-cards/refractor": missing.jpg\n'
                                    '  "base-cards/gold-refractr": x.jpg\n  "helix": http://example.com/h.jpg\n'
                                    '  "*/refractor": missing.jpg\n')
        os.makedirs(os.path.join(d, "images"))
        for fn in ("superfractor.png", "x.jpg", "base-cards-red-refractor.png"):
            with open(os.path.join(d, "images", fn), "wb") as fh:
                fh.write(b"img")
        stale = os.path.join(self.out, "synth-set", "images", "old.jpg")
        os.makedirs(os.path.dirname(stale))
        with open(stale, "wb") as fh:
            fh.write(b"old")
        data, report, _ = self.build(d)
        secs = dict((s["id"], s) for s in data["sections"])
        sup = [p for p in secs["base-cards"]["parallels"] if p["id"] == "superfractors"][0]
        self.assertEqual(sup["image"], "data/synth-set/images/superfractor.png")   # singular fallback
        self.assertIsNone(secs["helix"]["image"])                                   # http:// rejected
        w = data["warnings"]
        self.assertEqual(sum(1 for x in w if "'missing.jpg'" in x), 1)               # reported once
        self.assertTrue(any("http://" in x for x in w))
        self.assertTrue(any("'base-cards/gold-refractr'" in x and "matched no" in x for x in w))
        self.assertTrue(any("'base-cards-red-refractor.png'" in x and "not used" in x for x in w))
        self.assertFalse(os.path.exists(stale))
        self.assertIn("superfractor.png", report)


class ConfigTest(SynthSetMixin, unittest.TestCase):
    def test_yaml_error_names_line(self):
        d = self.make_set(yaml_text='name: X\naliases: {}\n  "TOPPS": "BASE CARDS"\n')
        with self.assertRaises(BuildError) as cm:
            load_config(d)
        self.assertIn("set.yaml line", str(cm.exception))

    def test_duplicate_key_is_an_error(self):
        d = self.make_set(yaml_text='name: X\naliases:\n  "A": "B"\nyear: 2026\naliases:\n')
        with self.assertRaises(BuildError) as cm:
            load_config(d)
        self.assertIn("'aliases' is written twice", str(cm.exception))

    def test_typos_and_bad_types_are_warnings(self):
        cfg, w = validate_config({
            "name": "X", "primary_format": "hobby", "alias": {},
            "formats": {"hobby": {"label": "Hobby", "packsperbox": 24, "packsPerBox": "20", "boxesPerCase": "x"},
                        "jumbo": 20},
            "overrides": {"sections": {"helix": {"catgory": "inserts", "tier": "ultra"}, "uv": "case-hits"}},
            "tiers": {"commonMax": "30", "foo": 1}, "images": {"a": {"b": 1}},
        })
        text = "\n".join(w)
        for needle in ("'primary_format'", "did you mean 'primaryFormat'", "'alias'", "'packsperbox'",
                       "'catgory'", "formats.jumbo", "overrides.sections.uv", "formats.hobby.boxesPerCase",
                       "'foo'", "images.a"):
            self.assertIn(needle, text)
        self.assertEqual(cfg["formats"]["hobby"]["packsPerBox"], 20)
        self.assertIsNone(cfg["formats"]["hobby"]["boxesPerCase"])
        self.assertEqual(cfg["overrides"]["sections"], {"helix": {"tier": "ultra"}})
        self.assertEqual(cfg["tiers"], {"commonMax": 30})

    def test_malformed_config_does_not_crash_build(self):
        d = self.make_set(yaml_text='name: X\nformats:\n  hobby: 20\noverrides:\n  sections:\n    helix: case-hits\n'
                                    'aliases:\n  "NOTHING": "BASE CARDS"\n  "HELIX": "NO SUCH SECTION"\n')
        data, _, _ = self.build(d)
        w = "\n".join(data["warnings"])
        self.assertIn("formats.hobby", w)
        self.assertIn("overrides.sections.helix", w)
        self.assertIn("'NOTHING' matched no odds row", w)
        self.assertIn("'HELIX' points to a section that does not exist", w)

    def test_scaffold_yaml_examples_uncomment_cleanly(self):
        text = scaffold_yaml("my-set", "My Set", 2027, "Baseball",
                             [{"id": "hobby", "label": "Hobby", "raw": "HOBBY"}])
        self.assertEqual(yaml.safe_load(text)["aliases"], None)
        uncommented = "\n".join(l[1:] if l.startswith("#  ") or l.startswith("#    ") else l
                                for l in text.splitlines())
        cfg = yaml.safe_load(uncommented)
        self.assertEqual(cfg["aliases"], {"TOPPS CHROME LEGENDS AUTOGRAPHS": "CHROME LEGEND AUTOGRAPHS"})
        self.assertEqual(cfg["overrides"]["sections"]["helix"], {"category": "case-hits"})
        self.assertEqual(cfg["tiers"], {"commonMax": 20})
        self.assertIn("make build SLUG=my-set", text)

    def test_new_validates_slug_and_leaves_nothing_on_failure(self):
        for bad in ("2027 Topps Chrome", "../escape", "Upper-Case"):
            code, _, err = run(["new", bad, "--checklist", self.checklist, "--sets-dir", self.sets])
            self.assertEqual(code, 1)
            self.assertIn("invalid slug", err)
        code, _, err = run(["new", "broken-set", "--checklist", os.path.join(self.src, "nope.pdf"),
                            "--sets-dir", self.sets])
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(os.path.join(self.sets, "broken-set")))
        bad_pdf = os.path.join(self.tmp, "bad.pdf")
        with open(bad_pdf, "w") as fh:
            fh.write("not a pdf")
        code, _, err = run(["new", "broken-set", "--checklist", bad_pdf, "--sets-dir", self.sets])
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(os.path.join(self.sets, "broken-set")))
        code, out, _ = run(["new", "good-set", "--checklist", self.checklist, "--sets-dir", self.sets])
        self.assertEqual(code, 0)
        self.assertIn("make build SLUG=good-set", out)

    def test_bad_set_does_not_stop_others(self):
        self.make_set("a-good")
        self.make_set("b-bad", yaml_text="name: [unclosed\n")
        self.make_set("c-good")
        code, out, err = run(["build", "--sets-dir", self.sets, "--out-dir", self.out, "--reports-dir", self.rep])
        self.assertEqual(code, 1)
        self.assertIn("[b-bad] FAILED: b-bad/set.yaml line", err)
        with open(os.path.join(self.out, "sets.json")) as fh:
            self.assertEqual([s["slug"] for s in json.load(fh)["sets"]], ["a-good", "c-good"])
        self.assertIn("have the same name", err)   # both detected as "2027 Topps Test"

    def test_explicit_slug_without_checklist_fails(self):
        os.makedirs(os.path.join(self.sets, "empty-set"))
        code, _, err = run(["build", "empty-set", "--sets-dir", self.sets, "--out-dir", self.out,
                            "--reports-dir", self.rep])
        self.assertEqual(code, 1)
        self.assertIn("FAILED: no checklist PDF", err)

    def test_removed_set_output_is_pruned(self):
        self.make_set("old-name")
        run(["build", "--sets-dir", self.sets, "--out-dir", self.out, "--reports-dir", self.rep])
        os.rename(os.path.join(self.sets, "old-name"), os.path.join(self.sets, "new-name"))
        os.makedirs(os.path.join(self.out, "old-name", "images"))
        code, out, _ = run(["build", "--sets-dir", self.sets, "--out-dir", self.out, "--reports-dir", self.rep])
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(os.path.join(self.out, "old-name.json")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "old-name")))
        self.assertFalse(os.path.exists(os.path.join(self.rep, "old-name.md")))
        with open(os.path.join(self.out, "sets.json")) as fh:
            self.assertEqual([s["slug"] for s in json.load(fh)["sets"]], ["new-name"])

    def test_index_order_is_deterministic(self):
        os.makedirs(self.out)
        for slug, name, year in (("2026-x-v1", "2026 X", 2026), ("2026-x", "2026 X", 2026), ("2025-y", "2025 Y", 2025)):
            os.makedirs(os.path.join(self.sets, slug))
            with open(os.path.join(self.out, slug + ".json"), "w") as fh:
                json.dump({"schemaVersion": 1, "slug": slug, "name": name, "year": year, "stats": {}}, fh)
        index = write_index(self.out, self.sets)
        self.assertEqual([s["slug"] for s in index["sets"]], ["2026-x", "2026-x-v1", "2025-y"])
        self.assertEqual(index["duplicateNames"], [["2026-x", "2026-x-v1"]])
        self.assertEqual(prune_outputs(self.sets, self.out, self.rep), [])

    def test_find_pdfs(self):
        d = os.path.join(self.sets, "names")
        os.makedirs(d)
        shutil.copy(self.checklist, os.path.join(d, "TOPPS-CHROME-CHECKLIST.PDF"))
        shutil.copy(self.odds, os.path.join(d, "ODDS.pdf"))
        self.assertEqual([os.path.basename(p) for p in find_pdfs(d)], ["TOPPS-CHROME-CHECKLIST.PDF", "ODDS.pdf"])
        d2 = os.path.join(self.sets, "content")
        os.makedirs(d2)
        shutil.copy(self.checklist, os.path.join(d2, "a.pdf"))
        shutil.copy(self.odds, os.path.join(d2, "b.pdf"))
        self.assertEqual([os.path.basename(p) for p in find_pdfs(d2)], ["a.pdf", "b.pdf"])

    def test_detect_meta_fallbacks(self):
        name, year, sport, _ = detect_meta("chrome-bball-26cubk", {}, None, None,
                                           ["BASE", "NBA DEBUT PATCH AUTOGRAPHS"])
        self.assertEqual((year, sport), (2026, "Basketball"))


if __name__ == "__main__":
    unittest.main()
