"""Orchestrates one set: PDFs -> site/data/<slug>.json + reports/<slug>.md."""
from __future__ import annotations

import datetime
import difflib
import glob
import json
import os
import re
import shutil
from collections import OrderedDict

import yaml

from . import classify
from .checklist import ChecklistError, parse_checklist
from .match import Matcher, parallel_display
from .names import clean_space, norm_token, raw_tokens, slugify, smart_title, unique_id
from .odds import OddsError, parse_odds

SCHEMA_VERSION = 1
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif")
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SPORTS = [
    ("baseball", "Baseball"), ("football", "Football"), ("basketball", "Basketball"),
    ("soccer", "Soccer"), ("hockey", "Hockey"), ("mls", "Soccer"), ("uefa", "Soccer"),
    ("premier league", "Soccer"), ("formula 1", "Racing"), ("f1", "Racing"), ("ufc", "MMA"),
    ("wwe", "Wrestling"), ("nba", "Basketball"), ("nfl", "Football"), ("mlb", "Baseball"),
    ("nhl", "Hockey"), ("wnba", "Basketball"),
]
LEAGUES = {"MLB": "Baseball", "NBA": "Basketball", "WNBA": "Basketball", "NFL": "Football",
           "NHL": "Hockey", "MLS": "Soccer"}

# set.yaml keys, per level (anything else is reported as a likely typo)
CONFIG_KEYS = ("name", "year", "sport", "brand", "primaryFormat", "formats", "tiers", "aliases",
               "overrides", "images")
FORMAT_KEYS = ("label", "packsPerBox", "boxesPerCase")
TIER_KEYS = ("commonMax", "shortPrintMax", "caseHitMax")
OVERRIDES_KEYS = ("sections",)
SECTION_OVERRIDE_KEYS = ("category", "tier", "kind", "name", "hidden")


class BuildError(Exception):
    pass


# ------------------------------------------------------------------ config / discovery

class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects a key written twice in one mapping (PyYAML silently keeps the
    last one, so a block pasted above the generated `aliases:` line would be thrown away)."""


def _construct_unique_mapping(loader, node, deep=False):
    seen = {}
    for key_node, _value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            first = seen.get(key)
        except TypeError:
            continue
        if first is not None:
            raise yaml.constructor.ConstructorError(
                None, None, "%r is written twice (first on line %d); keep only one %r line and put "
                "every entry under it" % (key, first + 1, key), key_node.start_mark)
        seen[key] = key_node.start_mark.line
    return loader.construct_mapping(node, deep=deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def load_config(set_dir):
    path = os.path.join(set_dir, "set.yaml")
    if not os.path.exists(path):
        return {}
    shown = os.path.join(os.path.basename(os.path.dirname(os.path.abspath(path))), "set.yaml")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.load(fh, Loader=_UniqueKeyLoader) or {}
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        problem = getattr(exc, "problem", None) or str(exc)
        where = " line %d" % (mark.line + 1) if mark is not None else ""
        raise BuildError("%s%s: %s (check indentation: spaces only, and that a `#` was removed "
                         "from the whole example line)" % (shown, where, problem))
    except UnicodeDecodeError as exc:
        raise BuildError("%s is not UTF-8 text: %s" % (shown, exc))
    if not isinstance(data, dict):
        raise BuildError("%s must contain `key: value` lines (got a %s)" % (shown, type(data).__name__))
    return data


def _typo(key, allowed, where):
    near = difflib.get_close_matches(str(key), allowed, n=1, cutoff=0.6)
    hint = " (did you mean %r?)" % near[0] if near else " (allowed: %s)" % ", ".join(allowed)
    return "set.yaml: unknown key %r%s%s; it is ignored" % (key, " in " + where if where else "", hint)


def _count(value, what, warnings):
    """A positive whole number from set.yaml, or None."""
    if value is None:
        return None
    if isinstance(value, bool):
        warnings.append("set.yaml: %s must be a whole number, not %r; ignored" % (what, value))
        return None
    try:
        n = int(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        warnings.append("set.yaml: %s must be a whole number, not %r; ignored" % (what, value))
        return None
    if n <= 0:
        warnings.append("set.yaml: %s must be positive, not %r; ignored" % (what, value))
        return None
    return n


def validate_config(cfg):
    """Check key names and value types. Returns (clean config, warnings): nothing in set.yaml
    can crash the build; anything unusable is reported and ignored."""
    warnings = []
    out = {}
    for key, val in cfg.items():
        if key not in CONFIG_KEYS:
            warnings.append(_typo(key, CONFIG_KEYS, ""))
            continue
        out[key] = val

    def mapping(key, val, where):
        if val is None:
            return {}
        if not isinstance(val, dict):
            warnings.append("set.yaml: %s must be a list of `key: value` lines, not %r; ignored" % (where, val))
            return {}
        return val

    for key in ("name", "sport", "brand", "primaryFormat"):
        if out.get(key) is not None and not isinstance(out[key], (str, int, float)):
            warnings.append("set.yaml: %s must be text; ignored" % key)
            out.pop(key)
    if out.get("year") is not None:
        out["year"] = _count(out["year"], "year", warnings)

    formats = OrderedDict()
    for fid, fc in mapping("formats", out.get("formats"), "formats").items():
        if fc is None:
            fc = {}
        if not isinstance(fc, dict):
            warnings.append("set.yaml: formats.%s must look like `{ label: Hobby, packsPerBox: 20, "
                            "boxesPerCase: 12 }`, not %r; ignored" % (fid, fc))
            continue
        clean = {}
        for k, v in fc.items():
            if k not in FORMAT_KEYS:
                warnings.append(_typo(k, FORMAT_KEYS, "formats.%s" % fid))
            elif k == "label":
                if v is not None:
                    clean[k] = str(v)
            else:
                clean[k] = _count(v, "formats.%s.%s" % (fid, k), warnings)
        formats[str(fid)] = clean
    out["formats"] = formats

    tiers = {}
    for k, v in mapping("tiers", out.get("tiers"), "tiers").items():
        if k not in TIER_KEYS:
            warnings.append(_typo(k, TIER_KEYS, "tiers"))
            continue
        n = _count(v, "tiers.%s" % k, warnings)
        if n is not None:
            tiers[k] = n
    out["tiers"] = tiers

    aliases = OrderedDict()
    for k, v in mapping("aliases", out.get("aliases"), "aliases").items():
        if k is None or v is None or isinstance(v, (dict, list)):
            warnings.append("set.yaml: alias %r -> %r must map odds-row text to a section name; ignored" % (k, v))
            continue
        aliases[str(k)] = str(v)
    out["aliases"] = aliases

    ov = mapping("overrides", out.get("overrides"), "overrides")
    for k in ov:
        if k not in OVERRIDES_KEYS:
            warnings.append(_typo(k, OVERRIDES_KEYS, "overrides"))
    sections = OrderedDict()
    for sid, sc in mapping("overrides.sections", ov.get("sections"), "overrides.sections").items():
        if sc is None:
            continue
        if not isinstance(sc, dict):
            warnings.append("set.yaml: overrides.sections.%s must look like `{ category: case-hits }`, "
                            "not %r; ignored" % (sid, sc))
            continue
        clean = {}
        for k, v in sc.items():
            if k not in SECTION_OVERRIDE_KEYS:
                warnings.append(_typo(k, SECTION_OVERRIDE_KEYS, "overrides.sections.%s" % sid))
            else:
                clean[k] = v
        sections[str(sid)] = clean
    out["overrides"] = {"sections": sections}

    images = OrderedDict()
    for k, v in mapping("images", out.get("images"), "images").items():
        if v is None or isinstance(v, (dict, list)):
            warnings.append("set.yaml: images.%s must be a file name or https:// URL; ignored" % k)
            continue
        images[str(k)] = str(v)
    out["images"] = images
    return out, warnings


def looks_like_odds(path):
    """True when the PDF's first page is dense with pack-odds values (1:341 ...)."""
    import pdfplumber
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                return False
            text = pdf.pages[0].extract_text() or ""
    except Exception:
        return False
    lines = [ln for ln in text.splitlines() if ln.strip()]
    with_odds = sum(1 for ln in lines if re.search(r"\b1:[\d,]+", ln))
    return with_odds >= 5 and with_odds >= 0.3 * len(lines)


def find_pdfs(set_dir):
    """(checklist PDF, odds PDF) in a set folder; file names are matched case-insensitively and,
    when the names don't tell, the two PDFs are told apart by their content."""
    try:
        names = sorted(fn for fn in os.listdir(set_dir) if fn.lower().endswith(".pdf"))
    except OSError:
        return None, None

    def pick(std, word):
        for fn in names:
            if fn.lower() == std:
                return fn
        for fn in names:
            if word in fn.lower():
                return fn
        return None

    checklist, odds = pick("checklist.pdf", "checklist"), pick("odds.pdf", "odds")
    if odds == checklist:
        odds = None
    rest = [fn for fn in names if fn not in (checklist, odds)]
    if (checklist is None or odds is None) and rest and len(names) <= 2:
        for fn in rest:
            is_odds = looks_like_odds(os.path.join(set_dir, fn))
            if is_odds and odds is None:
                odds = fn
            elif not is_odds and checklist is None:
                checklist = fn
    full = lambda fn: os.path.join(set_dir, fn) if fn else None
    return full(checklist), full(odds)


def detect_meta(slug, cfg, checklist_title, odds_title, section_names=()):
    name = cfg.get("name") or checklist_title or odds_title
    if not name:
        name = " ".join(w.capitalize() for w in slug.replace("_", "-").split("-"))
    name = clean_space(str(name))
    year = cfg.get("year")
    if year is None:
        m = re.search(r"\b(19|20)(\d\d)\b", name) or re.search(r"\b(19|20)(\d\d)\b", slug)
        if m:
            year = int(m.group(1) + m.group(2))
        else:
            # "chrome-bball-26cubk": a two-digit year at the start of a slug part
            m = re.search(r"(?:^|[-_])(\d\d)(?=[a-z]|[-_]|$)", slug.lower())
            if m and 10 <= int(m.group(1)) <= 60:
                year = 2000 + int(m.group(1))
    sport = cfg.get("sport")
    if not sport:
        low = " %s %s " % (name.lower(), slug.lower().replace("-", " "))
        for key, val in SPORTS:
            if re.search(r"\b%s\b" % re.escape(key), low):
                sport = val
                break
    if not sport and section_names:
        # league names inside section names ("NBA DEBUT PATCH AUTOGRAPHS")
        votes = {}
        for s in section_names:
            for tok in re.findall(r"[A-Z]+", str(s).upper()):
                if tok in LEAGUES:
                    votes[LEAGUES[tok]] = votes.get(LEAGUES[tok], 0) + 1
        if votes:
            sport = max(sorted(votes), key=lambda k: votes[k])
    brand = cfg.get("brand")
    if not brand:
        brand = "Bowman" if "bowman" in name.lower() else "Topps"
    return name, year, sport, brand


# ------------------------------------------------------------------ images

def _singular_id(pid):
    """'superfractors' -> 'superfractor', 'refractors-orange' -> 'refractor-orange'."""
    parts = []
    for p in pid.split("-"):
        if len(p) > 3 and p.endswith("s") and not p.endswith("ss"):
            p = p[:-1]
        parts.append(p)
    return "-".join(parts)


class ImageResolver(object):
    def __init__(self, set_dir, slug, cfg, out_dir, warnings):
        self.dir = os.path.join(set_dir, "images")
        self.slug = slug
        self.map = dict((str(k), str(v)) for k, v in (cfg.get("images") or {}).items())
        self.out_dir = out_dir
        self.warnings = warnings
        self.files = {}
        if os.path.isdir(self.dir):
            for fn in sorted(os.listdir(self.dir)):
                stem, ext = os.path.splitext(fn)
                if ext.lower() in IMAGE_EXTS:
                    self.files.setdefault(stem.lower(), fn)
        self.copied = set()
        self.reported = set()
        self.used_keys = set()
        self.used_files = set()
        self.assigned = []      # (target, image) for the report
        # Start from an empty copy so removed or renamed images don't linger on the site.
        dst = os.path.join(self.out_dir, self.slug, "images")
        if os.path.isdir(dst):
            shutil.rmtree(dst)

    def _publish(self, value):
        if re.match(r"^https://", value, re.I):
            return value
        if re.match(r"^http://", value, re.I):
            if value not in self.reported:
                self.reported.add(value)
                self.warnings.append("Image %r in set.yaml uses http://; only https:// URLs work on the "
                                     "published site, so it is ignored" % value)
            return None
        src = os.path.join(self.dir, value)
        if not os.path.isfile(src):
            if value not in self.reported:
                self.reported.add(value)
                self.warnings.append("Image %r listed in set.yaml not found in %s" % (value, self.dir))
            return None
        self.used_files.add(os.path.normcase(os.path.normpath(value)))
        dst_dir = os.path.join(self.out_dir, self.slug, "images")
        if value not in self.copied:
            os.makedirs(os.path.join(dst_dir, os.path.dirname(value)), exist_ok=True)
            shutil.copy2(src, os.path.join(dst_dir, value))
            self.copied.add(value)
        return "data/%s/images/%s" % (self.slug, value.replace(os.sep, "/"))

    def resolve(self, section_id, parallel_id=None, label=None):
        if parallel_id is None:
            keys = [("cfg", section_id), ("file", section_id)]
        else:
            keys = []
            for pid in [parallel_id] + ([_singular_id(parallel_id)] if _singular_id(parallel_id) != parallel_id else []):
                keys += [("cfg", "%s/%s" % (section_id, pid)), ("file", "%s--%s" % (section_id, pid)),
                         ("cfg", "*/%s" % pid), ("file", pid)]
            # the most specific match wins: section-level before generic, exact id before singular
            keys.sort(key=lambda k: 0 if "/" in k[1] and not k[1].startswith("*/") or "--" in k[1] else 1)
        for kind, key in keys:
            if kind == "cfg" and key in self.map:
                self.used_keys.add(key)
                url = self._publish(self.map[key])
                if url:
                    self.assigned.append((label or key, url))
                return url
            if kind == "file" and key.lower() in self.files:
                url = self._publish(self.files[key.lower()])
                if url:
                    self.assigned.append((label or key, url))
                return url
        return None

    def finish(self):
        """Warn about set.yaml image keys and image files that matched nothing (likely typos)."""
        for key in self.map:
            if key not in self.used_keys:
                self.warnings.append("set.yaml images key %r matched no section or parallel; check the ids "
                                     "in the report" % key)
        unused = []
        for fn in sorted(self.files.values()):
            if os.path.normcase(fn) not in self.used_files:
                unused.append(fn)
                self.warnings.append("Image file %r in sets/%s/images/ is not used: name it "
                                     "<section-id>--<parallel-id>%s, <parallel-id>%s or <section-id>%s"
                                     % (fn, self.slug, os.path.splitext(fn)[1], os.path.splitext(fn)[1],
                                        os.path.splitext(fn)[1]))
        return unused


# ------------------------------------------------------------------ helpers

def _sentence(s):
    s = clean_space(s)
    if s and s.upper() == s and any(ch.isalpha() for ch in s):
        s = s[:1] + s[1:].lower()
    return s


def _odds_map(row_odds, formats):
    out = OrderedDict()
    for f in formats:
        v = row_odds.get(f["id"]) if row_odds else None
        out[f["id"]] = v
    return out


def _fmt_odds(o):
    if o is None:
        return "-"
    return o["raw"]


def _head_difference(head_a, head_b):
    """Tokens of odds-name head A (display spelling) that head B lacks."""
    b = set(norm_token(t) for t in raw_tokens(head_b))
    return [t for t in raw_tokens(head_a) if norm_token(t) and norm_token(t) not in b]


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + "Z"


# ------------------------------------------------------------------ main build

def build_set(set_dir, out_dir, reports_dir, now=None, log=print):
    slug = os.path.basename(os.path.normpath(set_dir))
    raw_cfg = load_config(set_dir)
    cfg, warnings = validate_config(raw_cfg)
    checklist_pdf, odds_pdf = find_pdfs(set_dir)
    if not checklist_pdf:
        raise BuildError("no checklist PDF in %s" % set_dir)
    try:
        cl = parse_checklist(checklist_pdf)
    except ChecklistError as exc:
        raise BuildError(str(exc))
    od = None
    if odds_pdf:
        try:
            od = parse_odds(odds_pdf)
        except OddsError as exc:
            raise BuildError(str(exc))
    else:
        warnings.append("No odds PDF found; odds, parallels and tiers are unavailable")

    name, year, sport, brand = detect_meta(slug, cfg, cl["title"], od["title"] if od else None,
                                           [s["rawName"] for s in cl["sections"]])

    # ---- formats
    fmt_cfg = cfg.get("formats") or {}
    formats = []
    if od:
        for f in od["formats"]:
            c = fmt_cfg.get(f["id"]) or {}
            fo = OrderedDict()
            fo["id"] = f["id"]
            fo["label"] = str(c.get("label") or f["label"])
            fo["raw"] = f["raw"]
            fo["code"] = f["code"]
            fo["packsPerBox"] = c.get("packsPerBox")
            fo["boxesPerCase"] = c.get("boxesPerCase")
            fo["primary"] = False
            formats.append(fo)
        for key in fmt_cfg:
            if key not in [f["id"] for f in formats]:
                warnings.append("set.yaml formats.%s does not match any odds column (%s)"
                                % (key, ", ".join(f["id"] for f in formats)))
    primary_id = cfg.get("primaryFormat")
    if formats:
        if primary_id not in [f["id"] for f in formats]:
            if primary_id:
                warnings.append("primaryFormat %r not found; using %r" % (primary_id, formats[0]["id"]))
            primary_id = formats[0]["id"]
        for f in formats:
            f["primary"] = f["id"] == primary_id
    else:
        primary_id = None

    # ---- sections
    overrides = cfg["overrides"]["sections"]
    used_ids = set()
    sections = []
    for s in cl["sections"]:
        sec = OrderedDict()
        sec["id"] = unique_id(slugify(s["rawName"]), used_ids)
        sec["name"] = smart_title(s["rawName"])
        sec["rawName"] = s["rawName"]
        sec["group"] = s["group"]
        sec["kind"] = classify.section_kind(s["rawName"], s["group"])
        sec["category"] = None
        sec["tier"] = None
        sec["tierBasis"] = None
        sec["redemption"] = "REDEMPTION" in s["rawName"].upper()
        sec["cardCount"] = len(s["cards"])
        sec["rookieCount"] = sum(1 for c in s["cards"] if c["rookie"])
        sec["cards"] = s["cards"]
        sec["odds"] = None
        sec["oddsName"] = None
        sec["parallels"] = []
        sec["image"] = None
        sec["notes"] = [_sentence(n) for n in s.get("notes", [])]
        sections.append(sec)
    # An "insert" whose cards are exactly base cards (same number, same player) is an image
    # variation of the base set (e.g. MINIONS MLB #100 Aaron Judge).
    base_index = {}
    for sec in sections:
        if sec["kind"] == "base":
            for c in sec["cards"]:
                if c["code"]:
                    base_index.setdefault(c["code"], set()).add(tuple(p["name"] for p in c["players"]))
    for sec in sections:
        if sec["kind"] == "insert" and classify.is_base_variation(sec["cards"], base_index):
            sec["kind"] = "variation"
    for sec in sections:
        ov = overrides.get(sec["id"]) or {}
        if ov.get("kind"):
            if ov["kind"] not in classify.KINDS:
                warnings.append("Override kind %r for %s is not one of %s" % (ov["kind"], sec["id"], classify.KINDS))
            else:
                sec["kind"] = ov["kind"]
    for key in overrides:
        if key not in used_ids:
            near = difflib.get_close_matches(key, sorted(used_ids), n=1, cutoff=0.6)
            warnings.append("overrides.sections.%s does not match any section id%s"
                            % (key, " (did you mean %r?)" % near[0] if near else ""))

    # ---- odds matching
    unmatched = []
    mapping_log = []
    if od:
        matcher = Matcher(sections, cfg.get("aliases") or {})
        for prefix in matcher.alias_target_missing():
            warnings.append("set.yaml alias %r points to a section that does not exist; use the section's "
                            "raw name or id from the report" % prefix)
        par_ids = dict((s["id"], set()) for s in sections)
        heads = {}
        for row in od["rows"]:
            odds_obj = _odds_map(row["odds"], formats)
            m = matcher.match(row["name"])
            entry = OrderedDict([("rawName", row["rawName"]), ("section", None), ("parallel", None),
                                 ("how", m["how"]), ("score", m["score"]), ("reason", m["reason"])])
            mapping_log.append(entry)
            if m["section"] is None:
                unmatched.append(OrderedDict([("rawName", row["rawName"]), ("odds", odds_obj)]))
                continue
            sec = sections[m["section"]]
            entry["section"] = sec["rawName"]
            if m["redemption"]:
                sec["redemption"] = True
            tail = m["tail"]
            if not tail and sec["odds"] is None:
                sec["odds"] = odds_obj
                sec["oddsName"] = row["rawName"]
                entry["parallel"] = "(base)"
                continue
            if not tail:
                warnings.append("Second base-version odds row %r for section %r kept as a parallel"
                                % (row["rawName"], sec["rawName"]))
                pname = "Base (%s)" % smart_title(row["rawName"])
            else:
                pname = parallel_display(tail)
            twin = next((p for p in sec["parallels"] if p["id"] == slugify(pname)), None)
            if twin is not None:
                # Two odds rows give the same parallel name: they differ in the part matched to the
                # section (e.g. "... AUTOGRAPHS DRUSKI REFRACTORS ORANGE" / "... SPIKE LEE ...").
                mine = _head_difference(m.get("head", ""), heads.get(id(twin), ""))
                theirs = _head_difference(heads.get(id(twin), ""), m.get("head", ""))
                if mine:
                    pname = "%s %s" % (smart_title(" ".join(mine)), pname)
                if theirs and twin["name"] == parallel_display(tail):
                    par_ids[sec["id"]].discard(twin["id"])
                    twin["name"] = "%s %s" % (smart_title(" ".join(theirs)), twin["name"])
                    twin["id"] = unique_id(slugify(twin["name"]), par_ids[sec["id"]])
                    for e in mapping_log:
                        if e["rawName"] == twin["rawName"] and e["section"] == sec["rawName"]:
                            e["parallel"] = twin["name"]
            pid = unique_id(slugify(pname), par_ids[sec["id"]])
            if pid != slugify(pname):
                warnings.append("Duplicate parallel %r in section %r (odds row %r)" % (pname, sec["rawName"], row["rawName"]))
            par = OrderedDict()
            par["id"] = pid
            par["name"] = pname
            par["rawName"] = row["rawName"]
            par["odds"] = odds_obj
            par["formats"] = [fid for fid, v in odds_obj.items() if v is not None]
            par["image"] = None
            par["match"] = m["how"]
            sec["parallels"].append(par)
            heads[id(par)] = m.get("head", "")
            entry["parallel"] = pname
            for fid, v in odds_obj.items():
                if v is not None and v.get("error"):
                    warnings.append("Odds value %r for %r (%s): %s" % (v["raw"], row["rawName"], fid, v["error"]))
        for prefix in matcher.unused_aliases():
            if prefix not in matcher.alias_target_missing():
                warnings.append("set.yaml alias %r matched no odds row; it must be the exact start of an "
                                "odds row name as listed in the report" % prefix)

    # odds errors for base rows too
    for sec in sections:
        if sec["odds"]:
            for fid, v in sec["odds"].items():
                if v is not None and v.get("error"):
                    warnings.append("Odds value %r for %r (%s): %s" % (v["raw"], sec["oddsName"], fid, v["error"]))

    # ---- classification
    tiers_cfg = cfg.get("tiers") or {}
    fmt_label = dict((f["id"], f["label"]) for f in formats)
    for sec in sections:
        tier, basis = classify.compute_tier(sec, formats, primary_id, tiers_cfg) if formats else (None, None)
        sec["tier"] = tier
        sec["tierBasis"] = basis
        sec["category"] = classify.category_for(sec["kind"], tier)
        if od and sec["odds"] is None and not sec["parallels"]:
            sec["notes"].append("No odds listed for this section")
        elif basis and primary_id and basis["format"] != primary_id:
            sec["notes"].append("Not in %s packs; rarity based on %s odds"
                                % (fmt_label.get(primary_id, primary_id), fmt_label.get(basis["format"], basis["format"])))
        bad = classify.basis_source_error(sec, basis)
        if bad is not None:
            sec["notes"].append("Rarity is based on an odds value printed with an error in the source (%s)" % bad["raw"])
        no_odds = [p["name"] for p in sec["parallels"] if not p["formats"]]
        if no_odds:
            sec["notes"].append("Listed by Topps without odds in any format: %s" % ", ".join(no_odds))
        if sec["redemption"]:
            sec["notes"].append("Redemption card")
    # An insert without odds goes to the same tab as its sibling from another year
    # ("CLASS OF 2026 COOPERSTOWN CALLS" follows "CLASS OF 2025 COOPERSTOWN CALLS").
    for sec in sections:
        if sec["kind"] != "insert" or sec["tier"] is not None:
            continue
        key = classify.year_free_key(sec["rawName"])
        if key == clean_space(sec["rawName"].upper()):
            continue
        sib = next((t for t in sections if t is not sec and t["kind"] == "insert" and t["tier"] is not None
                    and classify.year_free_key(t["rawName"]) == key), None)
        if sib is not None and sib["category"] != sec["category"]:
            sec["category"] = sib["category"]
            sec["notes"].append("Shown with %s (same set, another year)" % sib["name"])
    for sec in sections:
        ov = overrides.get(sec["id"]) or {}
        if "tier" in ov:
            if ov.get("tier") not in classify.TIERS and ov.get("tier") is not None:
                warnings.append("Override tier %r for %s is not one of %s" % (ov.get("tier"), sec["id"], classify.TIERS))
            else:
                sec["tier"] = ov.get("tier")
                sec["category"] = classify.category_for(sec["kind"], sec["tier"])
        if ov.get("category"):
            if ov["category"] not in [c[0] for c in classify.CATEGORIES]:
                warnings.append("Override category %r for %s is not valid" % (ov["category"], sec["id"]))
            else:
                sec["category"] = ov["category"]
        if ov.get("name"):
            sec["name"] = str(ov["name"])

    hidden = set(k for k, v in overrides.items() if (v or {}).get("hidden"))
    visible = [s for s in sections if s["id"] not in hidden]

    # ---- images
    images = ImageResolver(set_dir, slug, cfg, out_dir, warnings)
    for sec in visible:
        sec["image"] = images.resolve(sec["id"], label=sec["id"])
        for par in sec["parallels"]:
            par["image"] = images.resolve(sec["id"], par["id"], label="%s / %s" % (sec["id"], par["id"]))
    unused_images = images.finish()

    all_warnings = list(cl["warnings"]) + (list(od["warnings"]) if od else []) + warnings

    data = OrderedDict()
    data["schemaVersion"] = SCHEMA_VERSION
    data["slug"] = slug
    data["name"] = name
    data["year"] = year
    data["sport"] = sport
    data["brand"] = brand
    data["generatedAt"] = now or _now()
    data["disclaimer"] = cl["disclaimer"] or (od["disclaimer"] if od else None)
    data["formats"] = formats
    data["categories"] = [OrderedDict([("id", cid), ("label", label),
                                       ("sectionCount", sum(1 for s in visible if s["category"] == cid))])
                          for cid, label in classify.CATEGORIES]
    data["sections"] = visible
    data["unmatchedOdds"] = unmatched
    data["warnings"] = all_warnings
    stats = OrderedDict()
    stats["sections"] = len(visible)
    stats["cards"] = sum(s["cardCount"] for s in visible)
    stats["rookies"] = sum(s["rookieCount"] for s in visible)
    stats["parallels"] = sum(len(s["parallels"]) for s in visible)
    stats["oddsRows"] = len(od["rows"]) if od else 0
    data["stats"] = stats

    report = render_report(data, sections, hidden, cl, od, mapping_log, checklist_pdf, odds_pdf,
                           images.assigned, unused_images)
    summary = OrderedDict([
        ("slug", slug), ("sections", stats["sections"]), ("cards", stats["cards"]),
        ("rookies", stats["rookies"]), ("parallels", stats["parallels"]),
        ("oddsRows", stats["oddsRows"]), ("matched", stats["oddsRows"] - len(unmatched)),
        ("unmatched", len(unmatched)), ("warnings", len(all_warnings)),
    ])
    return data, report, summary


def write_json_if_changed(path, data):
    """Write JSON; keep the previous generatedAt if nothing else changed (quiet git diffs)."""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                old = json.load(fh)
            a = dict(old)
            b = dict(data)
            a.pop("generatedAt", None)
            b.pop("generatedAt", None)
            if json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True):
                data["generatedAt"] = old.get("generatedAt", data["generatedAt"])
        except Exception:
            pass
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def _generated_sets(out_dir):
    """{slug: data} for the per-set JSON files in out_dir."""
    out = OrderedDict()
    for path in sorted(glob.glob(os.path.join(out_dir, "*.json"))):
        if os.path.basename(path) == "sets.json":
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            continue
        if not isinstance(d, dict) or d.get("schemaVersion") != SCHEMA_VERSION or "slug" not in d:
            continue
        if d["slug"] != os.path.splitext(os.path.basename(path))[0]:
            continue
        out[d["slug"]] = d
    return out


def prune_outputs(sets_dir, out_dir, reports_dir):
    """Remove generated output of sets whose folder no longer exists in sets_dir (renamed or
    deleted sets). Returns the removed slugs."""
    removed = []
    for slug in _generated_sets(out_dir):
        if os.path.isdir(os.path.join(sets_dir, slug)):
            continue
        os.remove(os.path.join(out_dir, slug + ".json"))
        if os.path.isdir(os.path.join(out_dir, slug)):
            shutil.rmtree(os.path.join(out_dir, slug))
        rep = os.path.join(reports_dir, slug + ".md")
        if os.path.isfile(rep):
            os.remove(rep)
        removed.append(slug)
    return removed


def write_index(out_dir, sets_dir=None):
    """Write sets.json listing the generated sets (only those with a folder in sets_dir, when
    given). Sorted newest year first, then name, then slug. Returns the index; sets that share
    a name are listed under "duplicateNames" in the returned dict (not written)."""
    sets = []
    for slug, d in _generated_sets(out_dir).items():
        if sets_dir is not None and not os.path.isdir(os.path.join(sets_dir, slug)):
            continue
        sets.append(OrderedDict([
            ("slug", d["slug"]), ("name", d.get("name")), ("year", d.get("year")),
            ("sport", d.get("sport")), ("cards", (d.get("stats") or {}).get("cards")),
            ("sections", (d.get("stats") or {}).get("sections")), ("generatedAt", d.get("generatedAt")),
        ]))
    sets.sort(key=lambda s: (-(s["year"] or 0), s["name"] or "", s["slug"]))
    index = OrderedDict([("schemaVersion", SCHEMA_VERSION), ("sets", sets)])
    with open(os.path.join(out_dir, "sets.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    by_name = {}
    for s in sets:
        by_name.setdefault((s["name"] or "").lower(), []).append(s["slug"])
    result = OrderedDict(index)
    result["duplicateNames"] = [slugs for slugs in by_name.values() if len(slugs) > 1]
    return result


# ------------------------------------------------------------------ report

def _md(s):
    return str(s if s is not None else "").replace("|", "\\|")


def render_report(data, all_sections, hidden, cl, od, mapping_log, checklist_pdf, odds_pdf,
                  images=(), unused_images=()):
    L = []
    st = data["stats"]
    L.append("# %s — pipeline report" % data["name"])
    L.append("")
    L.append("Generated by `make build` (`python -m pipeline build`). Do not edit; fix problems in "
             "`sets/%s/set.yaml`." % data["slug"])
    L.append("")
    cs = cl["stats"]
    L.append("- Checklist: `%s` (%d pages: %d main, %d overflow of which %d hold Rookie flags; %d card rows)"
             % (os.path.basename(checklist_pdf), cs["pages"], cs["mainPages"], cs["overflowPages"],
                cs.get("overflowPagesMapped", cs["overflowPages"]), cs["rows"]))
    L.append("- Rookie flags: %d inline, %d on overflow pages (%d mapped to rows)"
             % (cs["rookieFlagsInline"], cs["rookieFlagsOverflow"], cs["rookieFlagsOverflowMapped"]))
    L.append("- Columns: boundaries at x=%s, roles %s"
             % (cl["debug"]["boundaries"], json.dumps(cl["debug"]["roles"])))
    if od:
        L.append("- Odds: `%s` (%d rows, %s-aligned values)" % (os.path.basename(odds_pdf), len(od["rows"]), od["align"]))
    else:
        L.append("- Odds: none")
    L.append("- Sections: %d · cards: %d · rookie cards: %d · parallels: %d · odds rows: %d · unmatched: %d · warnings: %d"
             % (st["sections"], st["cards"], st["rookies"], st["parallels"], st["oddsRows"],
                len(data["unmatchedOdds"]), len(data["warnings"])))
    L.append("")
    if data["formats"]:
        L.append("## Formats")
        L.append("")
        L.append("| id | label | raw header | packs/box | boxes/case | primary |")
        L.append("|---|---|---|---|---|---|")
        for f in data["formats"]:
            L.append("| %s | %s | %s | %s | %s | %s |" % (f["id"], _md(f["label"]), _md(f["raw"]),
                                                       _md(f["packsPerBox"]), _md(f["boxesPerCase"]),
                                                       "yes" if f["primary"] else ""))
        L.append("")
    L.append("## Sections")
    L.append("")
    L.append("| # | id | section | group | kind | category | tier | tier basis | cards | RC | parallels | base odds |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    prim = next((f["id"] for f in data["formats"] if f["primary"]), None)
    for i, s in enumerate(all_sections, 1):
        basis = s["tierBasis"]
        b = "%s 1:%s" % (basis["format"], "{:,}".format(basis["n"])) if basis else ""
        base_odds = _fmt_odds(s["odds"].get(prim)) if (s["odds"] and prim) else ""
        L.append("| %d | %s%s | %s | %s | %s | %s | %s | %s | %d | %d | %d | %s |" % (
            i, s["id"], " (hidden)" if s["id"] in hidden else "", _md(s["rawName"]), _md(s["group"]),
            s["kind"], s["category"], s["tier"] or "—", b, s["cardCount"], s["rookieCount"],
            len(s["parallels"]), base_odds))
    L.append("")
    if od:
        L.append("## Odds rows → sections")
        L.append("")
        L.append("| # | odds row | section | parallel | match |")
        L.append("|---|---|---|---|---|")
        for i, e in enumerate(mapping_log, 1):
            how = e["how"] or "**unmatched**"
            if e["score"] is not None and e["how"] == "heuristic":
                how += " (%.2f)" % e["score"]
            L.append("| %d | %s | %s | %s | %s |" % (i, _md(e["rawName"]), _md(e["section"] or "—"),
                                                    _md(e["parallel"] or "—"), how))
        L.append("")
        L.append("## Unmatched odds rows")
        L.append("")
        um = [e for e in mapping_log if e["section"] is None]
        if um:
            for e in um:
                L.append("- `%s` — %s" % (e["rawName"], e["reason"]))
        else:
            L.append("None.")
        L.append("")
    L.append("## Sections without odds")
    L.append("")
    no = [s for s in all_sections if s["odds"] is None and not s["parallels"]]
    if no:
        for s in no:
            L.append("- %s (%s)" % (s["rawName"], s["id"]))
    else:
        L.append("None.")
    L.append("")
    L.append("## Images")
    L.append("")
    if images or unused_images:
        for target, url in images:
            L.append("- %s → `%s`" % (target, url))
        for fn in unused_images:
            L.append("- **unused:** `%s`" % fn)
    else:
        L.append("None (the site shows generated swatch cards).")
    L.append("")
    L.append("## Warnings")
    L.append("")
    if data["warnings"]:
        for w in data["warnings"]:
            L.append("- %s" % w)
    else:
        L.append("None.")
    L.append("")
    return "\n".join(L)


# ------------------------------------------------------------------ scaffold

def check_slug(slug):
    if not SLUG_RE.match(slug or ""):
        raise BuildError("invalid slug %r: use lowercase letters, digits and hyphens, e.g. "
                         "2027-topps-chrome-baseball" % slug)


def scaffold(sets_dir, slug, checklist, odds, name=None):
    check_slug(slug)
    set_dir = os.path.join(sets_dir, slug)
    if os.path.exists(os.path.join(set_dir, "set.yaml")):
        raise BuildError("%s already exists" % os.path.join(set_dir, "set.yaml"))
    for label, path in (("checklist", checklist), ("odds", odds)):
        if path and not os.path.isfile(path):
            raise BuildError("%s PDF not found: %s" % (label, path))
    # Parse both PDFs before creating anything, so a failed `new` leaves no empty folder behind.
    cl_title = od_title = None
    formats = []
    section_names = []
    if checklist:
        try:
            cl = parse_checklist(checklist)
        except ChecklistError as exc:
            raise BuildError(str(exc))
        cl_title = cl["title"]
        section_names = [s["rawName"] for s in cl["sections"]]
    if odds:
        try:
            od = parse_odds(odds)
        except OddsError as exc:
            raise BuildError(str(exc))
        od_title = od["title"]
        formats = od["formats"]
    cfg = {"name": name} if name else {}
    n, year, sport, _brand = detect_meta(slug, cfg, cl_title, od_title, section_names)
    created = not os.path.isdir(set_dir)
    try:
        os.makedirs(set_dir, exist_ok=True)
        if checklist and os.path.abspath(checklist) != os.path.abspath(os.path.join(set_dir, "checklist.pdf")):
            shutil.copy2(checklist, os.path.join(set_dir, "checklist.pdf"))
        if odds and os.path.abspath(odds) != os.path.abspath(os.path.join(set_dir, "odds.pdf")):
            shutil.copy2(odds, os.path.join(set_dir, "odds.pdf"))
        path = os.path.join(set_dir, "set.yaml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(scaffold_yaml(slug, n, year, sport, formats))
    except Exception:
        if created:
            shutil.rmtree(set_dir, ignore_errors=True)
        raise
    return path


def scaffold_yaml(slug, name, year, sport, formats):
    """Starter set.yaml. Empty sections are written as a bare `key:` line followed by commented
    examples, so removing the `#` from an example line gives valid YAML."""
    q = lambda s: json.dumps(s, ensure_ascii=False)
    L = []
    L.append("# Per-set configuration for the pipeline. How to edit this file: docs/ADDING_A_SET.md")
    L.append("# (every option: docs/SPEC.md). Rebuild with:  make build SLUG=%s" % slug)
    L.append("# To use an example below, delete the # at the start of its line (keep the spaces).")
    L.append("name: %s" % q(name))
    L.append("year: %s" % (year if year else "null"))
    L.append("sport: %s" % (q(sport) if sport else "null"))
    L.append("primaryFormat: %s" % (formats[0]["id"] if formats else "null"))
    L.append("")
    L.append("# One entry per odds column (keys are the detected format ids). Fill in packsPerBox /")
    L.append("# boxesPerCase from the sell sheet to get 'per box / per case' math and rarity tiers")
    L.append("# for that format; labels can be renamed freely.")
    L.append("formats:")
    for f in formats:
        L.append("  %s: { label: %s, packsPerBox: null, boxesPerCase: null }   # raw header: %s"
                 % (f["id"], q(f["label"]), f["raw"]))
    L.append("")
    L.append("# Rarity thresholds in packs (defaults: commonMax = packsPerBox, shortPrintMax = one case,")
    L.append("# caseHitMax = ten cases).")
    L.append("tiers:")
    L.append("#  commonMax: 20")
    L.append("")
    L.append("# Odds-row prefix -> checklist section raw name, for rows the heuristic matcher gets wrong.")
    L.append("aliases:")
    L.append("#  \"TOPPS CHROME LEGENDS AUTOGRAPHS\": \"CHROME LEGEND AUTOGRAPHS\"")
    L.append("")
    L.append("# Per-section fixes, keyed by section id (see reports/%s.md): category, tier, kind, name, hidden." % slug)
    L.append("overrides:")
    L.append("  sections:")
    L.append("#    helix: { category: case-hits }")
    L.append("")
    L.append("# Example images (files live in sets/%s/images/; URLs must start with https://)." % slug)
    L.append("images:")
    L.append("#  \"base-cards/gold-refractor\": gold.jpg")
    L.append("#  \"*/superfractor\": https://example.com/superfractor.jpg")
    L.append("")
    return "\n".join(L)
