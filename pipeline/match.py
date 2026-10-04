"""Match odds rows to checklist sections.

An odds row name is ``<variant of a section name> <parallel name>``. For every section we try
every split point ``k`` of the odds name: the first ``k`` tokens (the *head*) must explain the
section name, the remaining tokens (the *tail*) are the parallel name. The best
(section, k) pair wins. Scoring, in plain words:

* +1 for every section core token found in the head (case/plural/punctuation-insensitive);
* filler tokens (TOPPS, CHROME, sport words, CARD(S), REDEMPTION, ...) never score and are
  never penalised; REFRACTOR(S) inside a *section* name is filler too;
* -0.75 for every head token the section does not explain (-1 for an unexplained year);
* -0.5 for every section core token missing from the head; a missing year costs -1 (a year
  in the section name is distinctive: "1991 TOPPS FOOTBALL" is not the base set), a missing
  series marker (I, II, III, IV, SERIES) only -0.1, and a missing AUTOGRAPH / RELIC -1.5 when
  the odds name has no autograph/relic word at all (a plain insert row is not an autograph);
* +0.5 when both carry the same year; different years on both sides = no match;
* AUTOGRAPH / RELIC words in the odds name restrict candidates to sections of that kind;
  softer type words (SIGNATURES, PATCH, MATERIAL, ...) only cost -1 for sections of other kinds;
* split and joined spellings are the same word ("ULTRA VIOLET" = "ULTRAVIOLET");
* the head must end on a token that belongs to the section name.

``set.yaml`` aliases (exact odds-name prefix -> section raw name) are applied first.
"""
from __future__ import annotations

import re

from .names import (SECTION_SOFT_TOKENS, SOFT_TOKENS, SPECIAL_CASE, clean_space, fold_accents, is_year,
                    name_type_words, norm_token, normalize_quotes, raw_tokens, smart_title)

REDEMPTION_TOKENS = {"REDEMPTION"}
# Series markers an odds row often leaves out ("BASE CARDS GOLD" for section "BASE CARDS I").
LOW_MISSING_TOKENS = {"I", "II", "III", "IV", "SERIES"}
TYPE_CORE_TOKENS = {"AUTOGRAPH", "RELIC"}


def sub_tokens(raw_tok):
    """Normalised matching sub-tokens of one raw token (hyphenated words are split too)."""
    t = normalize_quotes(raw_tok)
    out = []
    whole = norm_token(t)
    if not whole:
        return out
    if "-" in whole and not whole.startswith("NON-"):
        for p in whole.split("-"):
            p = norm_token(p)
            if p:
                out.append(p)
    else:
        out.append(whole)
    return out


class SectionKey(object):
    def __init__(self, index, raw_name, kind):
        self.index = index
        self.raw_name = raw_name
        self.kind = kind
        toks = []
        for rt in raw_tokens(raw_name):
            toks.extend(sub_tokens(rt))
        self.tokens = toks
        # adjacent core tokens joined ("ULTRA" + "VIOLET" -> "ULTRAVIOLET")
        self.pairs = {}
        for a, b in zip(toks, toks[1:]):
            if not is_year(a) and not is_year(b):
                self.pairs.setdefault(a + b, (a, b))
        self.core = {}
        self.soft = set()
        self.years = set()
        for t in toks:
            if t in SOFT_TOKENS or t in SECTION_SOFT_TOKENS:
                self.soft.add(t)
            else:
                self.core[t] = self.core.get(t, 0) + 1
            if is_year(t):
                self.years.add(t)
        self.has_redemption = "REDEMPTION" in toks
        self.norm_name = fold_accents(clean_space(normalize_quotes(raw_name))).upper()


def allowed_kinds(name, strict=True):
    """Section kinds an odds row may match, from its autograph / relic words (None = any).

    strict: only the words AUTOGRAPH / RELIC (a hard constraint). Otherwise SIGNATURE(S), PATCH,
    MATERIAL, ... count too (used as a soft preference: "BILLBOARD MATERIAL" is an insert)."""
    has_auto, has_relic = name_type_words(name, strict=strict)
    strict_auto, strict_relic = name_type_words(name, strict=True)
    if has_auto and has_relic:
        if strict_auto and strict_relic:
            return {"autograph-relic"}
        # e.g. "PATCH AUTOGRAPHS": the relic word is a soft one, the section may sit in AUTOGRAPH
        if strict_auto or not strict_relic:
            return {"autograph", "autograph-relic"}
        return {"relic", "autograph-relic"}
    if has_auto:
        return {"autograph", "autograph-relic"}
    if has_relic:
        return {"relic", "autograph-relic"}
    return None


def _missing_penalty(tok, odds_typed):
    if is_year(tok):
        return 1.0
    if tok in LOW_MISSING_TOKENS:
        return 0.1
    if tok in TYPE_CORE_TOKENS and not odds_typed:
        return 1.5
    return 0.5


def score_split(sec, head_subs_per_tok, odds_years, odds_typed=True):
    """Best (score, k, matched) for section `sec` given odds tokens; None if no valid split.

    `odds_typed`: the odds name carries an autograph / relic word."""
    if odds_years and sec.years and not (odds_years & sec.years):
        return None
    best = None
    remaining = dict(sec.core)
    matched = 0
    unmatched_pen = 0.0
    year_bonus = 0.0
    soft_left = set(sec.soft)
    soft_bonus = 0.0
    for k, subs in enumerate(head_subs_per_tok, start=1):
        ends_on_section = False
        for t in subs:
            if remaining.get(t, 0) > 0:
                remaining[t] -= 1
                matched += 1
                ends_on_section = True
                if is_year(t):
                    year_bonus = 0.5
            elif t in sec.pairs and all(remaining.get(x, 0) > 0 for x in sec.pairs[t]):
                for x in sec.pairs[t]:
                    remaining[x] -= 1
                matched += 2
                ends_on_section = True
            elif t in sec.soft:
                ends_on_section = True
                if t in soft_left:
                    soft_left.discard(t)
                    soft_bonus += 0.05
            elif t in SOFT_TOKENS or t in REDEMPTION_TOKENS:
                pass
            elif is_year(t):
                unmatched_pen += 1.0
            else:
                unmatched_pen += 0.75
        if not ends_on_section or matched == 0:
            continue
        missing = 0.0
        for t, c in remaining.items():
            if c > 0:
                missing += _missing_penalty(t, odds_typed) * c
        score = matched + year_bonus + soft_bonus - unmatched_pen - missing
        cand = (score, matched, -k)
        if best is None or cand > best[0]:
            best = (cand, k, matched)
    return best


def strip_redemption(tokens):
    """Remove REDEMPTION [CARD|CARDS] from a token list. Returns (tokens, found)."""
    out = []
    found = False
    skip_card = False
    for t in tokens:
        u = norm_token(t)
        if u == "REDEMPTION":
            found = True
            skip_card = True
            continue
        if skip_card and u == "CARD":
            skip_card = False
            continue
        skip_card = False
        out.append(t)
    return out, found


class Matcher(object):
    def __init__(self, sections, aliases=None):
        """sections: list of dicts with 'rawName' and 'kind'."""
        self.keys = [SectionKey(i, s["rawName"], s.get("kind")) for i, s in enumerate(sections)]
        self.by_name = {}
        self.vocab = set()
        for k in self.keys:
            self.by_name.setdefault(k.norm_name, k)
            self.vocab.update(k.core)
        self.aliases = []
        self.alias_used = set()
        for prefix, target in (aliases or {}).items():
            p = fold_accents(clean_space(normalize_quotes(str(prefix)))).upper()
            t = fold_accents(clean_space(normalize_quotes(str(target)))).upper()
            self.aliases.append((p, t, str(prefix)))
        self.aliases.sort(key=lambda a: -len(a[0]))

    def alias_target_missing(self):
        """Alias prefixes (as written in set.yaml) whose target section does not exist."""
        return [orig for _p, t, orig in self.aliases if self._alias_key(t) is None]

    def unused_aliases(self):
        return [orig for p, _t, orig in self.aliases if p not in self.alias_used]

    def _alias_key(self, target):
        key = self.by_name.get(target)
        if key is None:
            # allow alias targets given as section ids too
            key = next((k for k in self.keys if _slug(k.raw_name) == target.lower()), None)
        return key

    def _join_compounds(self, subs):
        """Merge split spellings that the sections write as one word ("ULTRA VIOLET")."""
        subs = [list(x) for x in subs]
        for x in subs:
            if len(x) == 2 and x[0] + x[1] in self.vocab:
                x[:] = [x[0] + x[1]]
        for i in range(len(subs) - 1):
            a, b = subs[i], subs[i + 1]
            if len(a) == 1 and len(b) == 1 and a[0] + b[0] in self.vocab \
                    and not is_year(a[0]) and not is_year(b[0]):
                subs[i + 1] = [a[0] + b[0]]
                subs[i] = []
        return subs

    def match(self, odds_name):
        """Return dict(section=index|None, parallel=raw tail str, how=..., redemption=bool,
        score=float, reason=str)."""
        name = clean_space(normalize_quotes(odds_name))
        upper = fold_accents(name).upper()
        result = {"section": None, "tail": "", "head": "", "how": None, "redemption": False,
                  "score": None, "reason": ""}
        if not name:
            result["reason"] = "empty name"
            return result
        # 1. aliases
        for prefix, target, _orig in self.aliases:
            if upper == prefix or upper.startswith(prefix + " "):
                self.alias_used.add(prefix)
                key = self._alias_key(target)
                if key is None:
                    result["reason"] = "alias target %r not found" % target
                    return result
                tail = name[len(prefix):].strip()
                toks, red = strip_redemption(raw_tokens(tail))
                result.update(section=key.index, tail=" ".join(toks), head=name[:len(prefix)].strip(),
                              how="alias", redemption=red or key.has_redemption)
                return result
        # 2. whole name equals a section name
        key = self.by_name.get(upper)
        if key is not None:
            result.update(section=key.index, tail="", how="exact", redemption=key.has_redemption)
            return result
        toks = raw_tokens(name)
        kinds = allowed_kinds(name)
        soft_kinds = allowed_kinds(name, strict=False)
        odds_years = set(t for rt in toks for t in sub_tokens(rt) if is_year(t))
        subs = self._join_compounds([sub_tokens(t) for t in toks])
        best = None
        for key in self.keys:
            if kinds is not None and key.kind is not None and key.kind not in kinds:
                continue
            r = score_split(key, subs, odds_years, soft_kinds is not None)
            if r is None:
                continue
            cand, k, matched = r
            if soft_kinds is not None and key.kind is not None and key.kind not in soft_kinds:
                cand = (cand[0] - 1.0,) + tuple(cand[1:])
            if best is None or cand > best[0]:
                best = (cand, k, key)
        if best is None or best[0][0] <= 0:
            result["reason"] = "no section explains this name" if best is None else \
                "best candidate %r scored too low (%.2f)" % (best[2].raw_name, best[0][0])
            return result
        cand, k, key = best
        # filler right after the section name ("BASE" + "CARDS REFRACTOR") is not part of the
        # parallel name
        while k < len(toks) and [t for t in sub_tokens(toks[k])] == ["CARD"]:
            k += 1
        head = toks[:k]
        tail, red = strip_redemption(toks[k:])
        if len(tail) == 1 and norm_token(tail[0]) == "BASE":
            tail = []   # "PROTONYX BASE" = the base version of PROTONYX
        how = "exact" if clean_space(" ".join(head)).upper() == key.norm_name else "heuristic"
        result.update(section=key.index, tail=" ".join(tail), head=" ".join(head), how=how,
                      redemption=red or key.has_redemption or
                      any(norm_token(t) == "REDEMPTION" for t in head),
                      score=round(cand[0], 2))
        return result


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def parallel_display(tail):
    """Display name of a parallel. Known parallel words get their canonical spelling even in
    mixed-case odds sheets ("SuperFractor" -> "Superfractor", "Superfractors" -> "Superfractors")."""
    s = smart_title(tail)
    out = []
    for w in s.split(" "):
        up = w.upper()
        if up in SPECIAL_CASE and len(up) > 4:
            w = SPECIAL_CASE[up]
        elif up.endswith("S") and up[:-1] in SPECIAL_CASE and len(up) > 5:
            w = SPECIAL_CASE[up[:-1]] + w[-1]
        out.append(w)
    return " ".join(out)
