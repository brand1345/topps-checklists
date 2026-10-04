"""Section kind / category / rarity tier."""
from __future__ import annotations

import math
import re
from collections import OrderedDict

from .names import name_type_words, normalize_quotes

CATEGORIES = [
    ("base", "Base & Parallels"),
    ("inserts", "Inserts"),
    ("case-hits", "Case Hits"),
    ("autographs", "Autographs"),
    ("relics", "Relics"),
]
KINDS = ("base", "variation", "insert", "autograph", "relic", "autograph-relic")
TIERS = ("common", "short-print", "case-hit", "ultra")
DEFAULT_PACKS_PER_BOX = 20
DEFAULT_BOXES_PER_CASE = 12


def _group_key(group):
    t = normalize_quotes(group or "").upper().replace("-", " ")
    t = re.sub(r"[^A-Z ]", " ", t)
    words = []
    for w in t.split():
        if len(w) > 3 and w.endswith("S") and not w.endswith("SS"):
            w = w[:-1]
        words.append(w)
    return " ".join(words)


def _is_variation_name(raw):
    u = normalize_quotes(raw).upper()
    return ("VARIATION" in u or "SUPER SHORT PRINT" in u or u.startswith("BASE CARD"))


def _name_kind(raw):
    """Kind implied by a section name alone, or None."""
    has_auto, has_relic = name_type_words(raw)
    if has_auto and has_relic:
        return "autograph-relic"
    if has_auto:
        return "autograph"
    if has_relic:
        return "relic"
    u = normalize_quotes(raw).upper()
    if re.search(r"\bINSERTS?\b", u):
        return "insert"
    if re.search(r"\bSHORT PRINTS?\b|\bSSP\b|\bVARIATIONS?\b", u):
        return "variation"
    return None


def section_kind(raw_name, group):
    g = _group_key(group)
    if g in ("AUTOGRAPH RELIC", "RELIC AUTOGRAPH", "AUTOGRAPHED RELIC", "AUTOGRAPH MEMORABILIA"):
        return "autograph-relic"
    if g in ("RELIC", "MEMORABILIA"):
        has_auto, _ = name_type_words(raw_name)
        return "autograph-relic" if has_auto else "relic"
    if g == "AUTOGRAPH":
        return "autograph"
    if g == "INSERT":
        return "variation" if _is_variation_name(raw_name) else "insert"
    # BASE group (or no / unknown group): sections are base subsets unless the name says
    # otherwise (some checklists put every section under BASE).
    nk = _name_kind(raw_name)
    if g == "BASE" or g == "PARALLEL":
        if nk is not None:
            return nk
        if g == "PARALLEL":
            return "variation"
        return "base"
    if nk is not None:
        return nk
    if g == "VARIATION":
        return "variation"
    return "base" if normalize_quotes(raw_name).upper().startswith("BASE") else "insert"


def basis_source_error(section, basis):
    """The odds value a tierBasis was taken from, when that value carries a source error."""
    if not basis:
        return None
    fid, n = basis["format"], basis["n"]
    vals = [(section.get("odds") or {}).get(fid)] + \
        [(p.get("odds") or {}).get(fid) for p in section.get("parallels", [])]
    vals = [v for v in vals if isinstance(v, dict) and v.get("n") == n]
    if vals and all(v.get("error") for v in vals):
        return vals[0]
    return None


def year_free_key(raw):
    """Section name without 4-digit years ("CLASS OF 2026 COOPERSTOWN CALLS" -> "CLASS OF COOPERSTOWN CALLS")."""
    u = normalize_quotes(raw or "").upper()
    return re.sub(r"\s+", " ", re.sub(r"\b(19|20)\d\d\b", " ", u)).strip()


def is_base_variation(cards, base_index):
    """True when every card has a plain-number code and matches the base card with that number
    and the same player(s): an image-variation set printed as an insert (e.g. "MINIONS MLB")."""
    if not cards:
        return False
    for c in cards:
        code = c.get("code") or ""
        if not re.match(r"^\d+$", code):
            return False
        names = tuple(p.get("name", "") for p in c.get("players", []))
        if names not in base_index.get(code, ()):
            return False
    return True


def category_for(kind, tier):
    if kind in ("base", "variation"):
        return "base"
    if kind == "insert":
        return "case-hits" if tier in ("case-hit", "ultra") else "inserts"
    if kind == "autograph":
        return "autographs"
    return "relics"


def thresholds(packs_per_box, boxes_per_case, tiers_cfg=None):
    p = packs_per_box or DEFAULT_PACKS_PER_BOX
    c = p * (boxes_per_case or DEFAULT_BOXES_PER_CASE)
    t = {"commonMax": p, "shortPrintMax": c, "caseHitMax": 10 * c}
    for k in ("commonMax", "shortPrintMax", "caseHitMax"):
        if tiers_cfg and tiers_cfg.get(k) is not None:
            t[k] = tiers_cfg[k]
    return t


def tier_for_n(n, th):
    if n is None:
        return None
    if n <= th["commonMax"]:
        return "common"
    if n <= th["shortPrintMax"]:
        return "short-print"
    if n <= th["caseHitMax"]:
        return "case-hit"
    return "ultra"


def round_rate(x):
    """Round a per-box / per-case rate to 4 decimals, keeping 4 significant figures for tiny
    rates (1 in 2,848,800 packs is 7.021e-06 per box, not 0.0)."""
    if not x:
        return x
    decimals = max(4, 3 - int(math.floor(math.log10(abs(x)))))
    return round(x, decimals)


def _n(v):
    if isinstance(v, dict):
        return v.get("n")
    return None


def compute_tier(section, formats, primary_id, tiers_cfg=None):
    """Return (tier, tierBasis) for a section dict holding 'odds' and 'parallels'."""
    fmt_by_id = OrderedDict((f["id"], f) for f in formats)
    primary = fmt_by_id.get(primary_id)

    def representative(fid):
        """n of the base version in format fid, else the most common parallel."""
        base = section.get("odds") or {}
        n = _n(base.get(fid))
        if n:
            return n, "base"
        ns = [_n((p.get("odds") or {}).get(fid)) for p in section.get("parallels", [])]
        ns = [x for x in ns if x]
        if ns:
            return min(ns), "parallel"
        return None, None

    chosen_fid = None
    n = None
    if primary is not None:
        n, _ = representative(primary_id)
        if n:
            chosen_fid = primary_id
    if not n:
        best = None
        for fid in fmt_by_id:
            m, _ = representative(fid)
            if m and (best is None or m < best[0]):
                best = (m, fid)
        if best is None:
            return None, None
        n, chosen_fid = best
    fmt = fmt_by_id[chosen_fid]
    ppb = fmt.get("packsPerBox")
    bpc = fmt.get("boxesPerCase")
    if (ppb is None or bpc is None) and primary is not None:
        ppb = ppb if ppb is not None else primary.get("packsPerBox")
        bpc = bpc if bpc is not None else primary.get("boxesPerCase")
    th = thresholds(ppb, bpc, tiers_cfg)
    tier = tier_for_n(n, th)
    own_ppb = fmt.get("packsPerBox")
    own_bpc = fmt.get("boxesPerCase")
    basis = OrderedDict()
    basis["format"] = chosen_fid
    basis["n"] = n
    basis["perBox"] = round_rate(own_ppb / float(n)) if own_ppb else None
    basis["perCase"] = round_rate(own_ppb * own_bpc / float(n)) if (own_ppb and own_bpc) else None
    return tier, basis
