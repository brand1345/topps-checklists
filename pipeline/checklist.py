"""Checklist PDF -> groups / sections / cards.

The checklist is a spreadsheet printed to PDF. Everything here is driven by word/char
positions, never by hard-coded coordinates:

* lines are built by clustering words on their ``top`` coordinate;
* bold lines are headers (group or section), italic / "Checklists provided by" lines are the
  disclaimer, the first bold non-header line on page 1 is the title;
* card-row columns (code / name / team) are found by looking for vertical gutters that no
  character of any row crosses;
* "Rookie" flags are read either from a trailing column on the same line or from trailing
  overflow pages (pages that hold nothing but flags), mapped back to rows by page + y.
"""
from __future__ import annotations

import bisect
import re
from collections import OrderedDict

import pdfplumber

from .names import clean_name, clean_space, clean_team, normalize_quotes

LINE_TOL = 2.0
ROOKIE_FLAGS = {"ROOKIE", "RC", "ROOKIE CARD", "(RC)"}
# Words of a spreadsheet column-header row ("Card # | Player | Team | Rookie").
COLUMN_HEADER_WORDS = {
    "CARD": "code", "#": "code", "CARD#": "code", "NO": "code", "NO.": "code", "NUMBER": "code",
    "PLAYER": "name", "PLAYERS": "name", "NAME": "name", "SUBJECT": "name",
    "TEAM": "team", "TEAMS": "team", "CLUB": "team", "COUNTRY": "team",
    "ROOKIE": "flag", "RC": "flag", "SUBSET": "flag", "NOTES": "flag", "POSITION": "flag", "POS": "flag",
}
FOOTER_RE = re.compile(r"^(page\s*)?\d+\s*(of|/)\s*\d+$|^page\s*\d+$", re.I)
CONTINUED_RE = re.compile(r"\s*[\(\[]?\s*\b(?:CONTINUED|CONT'D|CONT\.)\s*[\)\]]?\s*$", re.I)
MAX_CARD_PLAYERS = 4
GROUP_VOCAB = {
    "BASE", "INSERT", "AUTOGRAPH", "RELIC", "AUTOGRAPH RELIC", "RELIC AUTOGRAPH",
    "AUTOGRAPHED RELIC", "PARALLEL", "MEMORABILIA", "AUTOGRAPH MEMORABILIA", "HIT", "VARIATION",
}
DISCLAIMER_RE = re.compile(r"checklists?\b.{0,40}\bprovided\b", re.I)
CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-\./#]*$")


class ChecklistError(Exception):
    pass


def font_style(fontname: str) -> str:
    f = (fontname or "").lower()
    if "bold" in f or "black" in f or "heavy" in f or "semibold" in f or "demi" in f:
        return "bold"
    if "italic" in f or "oblique" in f:
        return "italic"
    return "regular"


def group_key(text: str) -> str:
    t = normalize_quotes(text).upper().replace("-", " ")
    t = re.sub(r"[^A-Z ]", " ", t)
    words = []
    for w in t.split():
        if len(w) > 3 and w.endswith("S") and not w.endswith("SS"):
            w = w[:-1]
        words.append(w)
    return " ".join(words)


def is_group_vocab(text: str) -> bool:
    return group_key(text) in GROUP_VOCAB


def is_code_like(text: str) -> bool:
    if not text or " " in text or len(text) > 16:
        return False
    if not CODE_RE.match(text):
        return False
    if any(ch.isdigit() for ch in text) or "-" in text:
        return True
    return text.isupper() and len(text) <= 6


class Line(object):
    __slots__ = ("page", "top", "bottom", "words", "chars", "style", "kind", "text", "flag",
                 "cells", "rookie", "tag", "furniture", "size")

    def __init__(self, page, words):
        self.page = page
        self.words = sorted(words, key=lambda w: w["x0"])
        self.top = min(w["top"] for w in words)
        self.bottom = max(w["bottom"] for w in words)
        self.chars = []
        styles = [font_style(w.get("fontname", "")) for w in self.words]
        if all(s == "bold" for s in styles):
            self.style = "bold"
        elif all(s == "italic" for s in styles):
            self.style = "italic"
        elif styles.count("bold") > len(styles) / 2.0:
            self.style = "bold"
        else:
            self.style = "regular"
        self.kind = None
        self.text = clean_space(" ".join(w["text"] for w in self.words))
        self.flag = 0          # number of trailing words that are a flag/tag cell (not name/team)
        self.cells = None
        self.rookie = False
        self.tag = None        # text of a trailing non-Rookie flag-column value ("Future Stars")
        self.furniture = False  # repeated page header/footer line
        sizes = sorted(float(w.get("size") or 0) for w in self.words)
        self.size = sizes[len(sizes) // 2] if sizes else 0.0

    def __repr__(self):
        return "<Line p%d %.1f %s %r>" % (self.page + 1, self.top, self.kind, self.text)


def _cluster_lines(page_index, words):
    lines = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(w["top"] - lines[-1][-1]["top"]) <= LINE_TOL:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [Line(page_index, ws) for ws in lines]


def read_pages(pdf):
    """Return a list of pages, each a list of Line objects (off-page spill removed)."""
    pages = []
    for pi, page in enumerate(pdf.pages):
        width = float(page.width)
        try:
            words = page.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False,
                                       use_text_flow=False, x_tolerance=1.5)
        except Exception:  # pragma: no cover - pdfplumber quirks
            words = []
        lines = _cluster_lines(pi, words) if words else []
        kept = []
        for ln in lines:
            # Lines with text printed outside the page are spill from a neighbouring page
            # (e.g. the disclaimer of page 1 repeated at negative x on the overflow page).
            if any(w["x1"] <= 0.5 or w["x0"] >= width - 0.5 for w in ln.words):
                continue
            kept.append(ln)
        chars = []
        for ci, c in enumerate(page.chars):
            if c["x1"] > 0 and c["x0"] < width:
                c = dict(c)
                c["_i"] = ci          # content-stream order (reading order inside a cell)
                chars.append(c)
        chars.sort(key=lambda c: c["top"])
        char_tops = [c["top"] for c in chars]
        for ln in kept:
            lo = bisect.bisect_left(char_tops, ln.top - LINE_TOL)
            hi = bisect.bisect_right(char_tops, ln.top + LINE_TOL)
            ln.chars = sorted((c for c in chars[lo:hi] if c["x0"] >= ln.words[0]["x0"] - 1
                               and c["x1"] <= ln.words[-1]["x1"] + 1),
                              key=lambda c: c["x0"])
        pages.append({"index": pi, "width": width, "height": float(page.height), "lines": kept})
    return pages


def _flag_text(ln):
    """Return (n_words, flag) if the line ends with a Rookie flag."""
    ws = ln.words
    if len(ws) >= 3 and (ws[-2]["text"] + " " + ws[-1]["text"]).upper() == "ROOKIE CARD":
        return 2
    if len(ws) >= 2 and ws[-1]["text"].upper() in ROOKIE_FLAGS:
        gap = ws[-1]["x0"] - ws[-2]["x1"]
        if gap > 2.0:
            return 1
    return 0


def _is_flag_only(ln):
    return ln.text.upper() in ROOKIE_FLAGS


# ------------------------------------------------------------------ classification

def is_column_header_row(text):
    """True for a spreadsheet column-header row such as "Card # Player Team Rookie"."""
    toks = [t for t in re.split(r"\s+", normalize_quotes(text).upper().strip()) if t]
    if len(toks) < 2:
        return False
    roles = set()
    for t in toks:
        role = COLUMN_HEADER_WORDS.get(t.strip(":"))
        if role is None:
            return False
        roles.add(role)
    return len(roles & {"code", "name", "team"}) >= 2


def mark_furniture(pages):
    """Mark lines repeated at the same y near the top/bottom of most pages (running page
    titles, repeated column-header rows, footers such as "Page 1 of 2").

    Bold lines only count when they look like a title (a year, "Topps" or "Checklist"): a
    group/section header repeated after a page break is handled when sections are assembled."""
    content_pages = [p for p in pages if p["lines"]]
    if len(content_pages) < 2:
        return
    seen = {}
    for p in content_pages:
        keys = set()
        for ln in p["lines"]:
            if ln.text.upper() in ROOKIE_FLAGS or not _furniture_candidate(ln):
                continue
            band = 0.12 * p["height"]
            if band < ln.top < p["height"] - band:
                continue
            keys.add((int(round(ln.top / 3.0)), ln.text.lower()))
        for k in keys:
            seen[k] = seen.get(k, 0) + 1
    need = max(2, 0.5 * len(content_pages))
    for p in content_pages:
        for ln in p["lines"]:
            k = (int(round(ln.top / 3.0)), ln.text.lower())
            if seen.get(k, 0) >= need and _furniture_candidate(ln):
                ln.furniture = True


def _furniture_candidate(ln):
    if ln.style != "bold":
        return True
    return (not is_group_vocab(ln.text)
            and bool(re.search(r"\b(19|20)\d\d\b", ln.text) or re.search(r"topps|checklist", ln.text, re.I)))


def _fallback_headers(pages):
    """Header candidates for checklists whose headers are not in a bold font: lines in a larger
    type than the card rows, or short all-caps single-cell lines."""
    sizes = sorted(ln.size for p in pages for ln in p["lines"] if ln.size)
    med = sizes[len(sizes) // 2] if sizes else 0.0
    out = set()
    for p in pages:
        for ln in p["lines"]:
            if ln.style == "italic" or ln.furniture:
                continue
            if med and ln.size >= med + 0.75:
                out.add(id(ln))
                continue
            t = ln.text
            if not (t.upper() == t and any(ch.isalpha() for ch in t) and len(t) <= 60):
                continue
            if is_code_like(ln.words[0]["text"]) and any(ch.isdigit() for ch in ln.words[0]["text"]):
                continue
            size = ln.size or 8.0
            gaps = [b["x0"] - a["x1"] for a, b in zip(ln.words, ln.words[1:])]
            if all(g < 1.5 * size for g in gaps) and t.upper() not in ROOKIE_FLAGS:
                out.add(id(ln))
    return out


def classify_lines(pages, warnings):
    """Assign kinds: title, disclaimer, header, row, flag. Returns (title, disclaimer)."""
    title = None
    disclaimer_parts = []
    seen_header = False
    mark_furniture(pages)
    any_bold = any(ln.style == "bold" for p in pages for ln in p["lines"])
    fallback = set() if any_bold else _fallback_headers(pages)
    if fallback:
        warnings.append("No bold header lines found; section headers were guessed from type size / "
                        "all-caps lines. Check the section list in this report.")
    for page in pages:
        lines = page["lines"]
        i = 0
        while i < len(lines):
            ln = lines[i]
            if ln.style == "italic" and not seen_header:
                ln.kind = "disclaimer"
                disclaimer_parts.append(ln.text)
                i += 1
                continue
            if ln.style == "italic" and DISCLAIMER_RE.search(ln.text):
                ln.kind = "disclaimer"
                i += 1
                continue
            if ln.style == "italic":
                # e.g. "EXCLUSIVE TO HOBBY AND VALUE CONFIGURATION" under a section header
                ln.kind = "note"
                i += 1
                continue
            if DISCLAIMER_RE.search(ln.text):
                ln.kind = "disclaimer"
                parts = [ln.text]
                j = i + 1
                while (j < len(lines) and len(parts) < 4 and not parts[-1].rstrip("*").endswith(".")
                       and lines[j].style == ln.style and not is_group_vocab(lines[j].text)
                       and lines[j].top - lines[j - 1].top < 3 * max(1.0, lines[j - 1].bottom - lines[j - 1].top) + 6):
                    lines[j].kind = "disclaimer"
                    parts.append(lines[j].text)
                    j += 1
                if not disclaimer_parts:
                    disclaimer_parts.extend(parts)
                i = j
                continue
            is_header = ln.style == "bold" or id(ln) in fallback
            if (is_header and not seen_header and title is None and page["index"] == 0
                    and not is_group_vocab(ln.text)
                    and (re.search(r"\b(19|20)\d\d\b", ln.text) or re.search(r"topps|checklist", ln.text, re.I))):
                ln.kind = "title"
                title = ln.text
                i += 1
                continue
            if ln.furniture or is_column_header_row(ln.text) or FOOTER_RE.match(ln.text.strip()):
                ln.kind = "furniture"
                i += 1
                continue
            if is_header:
                ln.kind = "header"
                seen_header = True
                i += 1
                continue
            if _is_flag_only(ln):
                ln.kind = "flag"
            else:
                ln.kind = "row"
            i += 1
    disclaimer = clean_space(" ".join(disclaimer_parts)).strip("* ") or None
    if title:
        title = re.sub(r"\s*checklist\s*$", "", title, flags=re.I).strip()
    return title, disclaimer


def classify_pages(pages):
    """Mark each page as main ("M") or overflow ("O": Rookie-column overflow, or empty).

    An overflow page has no headers and all its text sits in one narrow column. Values in that
    column other than Rookie flags (e.g. "Future Stars") become kind "tag", never card rows."""
    for page in pages:
        content = [ln for ln in page["lines"] if ln.kind in ("header", "row", "flag", "note")]
        if any(ln.kind in ("header", "note") for ln in content):
            page["kind"] = "M"
            continue
        if all(ln.kind == "flag" for ln in content):
            page["kind"] = "O"   # only flags or nothing at all
            continue
        x0 = min(ln.words[0]["x0"] for ln in content)
        x1 = max(ln.words[-1]["x1"] for ln in content)
        if x1 - x0 < 0.25 * page["width"] and all(len(ln.text) <= 30 for ln in content):
            page["kind"] = "O"
            for ln in content:
                if ln.kind == "row":
                    ln.kind = "tag"
        else:
            page["kind"] = "M"


def _flag_match_count(flags, rows):
    n = 0
    for fl in flags:
        if any(abs(r.top - fl.top) <= 2.5 for r in rows):
            n += 1
    return n


def map_overflow(pages, rows_by_page, warnings):
    """Return {overflow page index: main page index} for overflow pages holding flags.

    Interleaved layouts ("over, then down": M O M O ...) map every overflow page to the main page
    before it. Trailing layouts ("down, then over": M M M O O O) are aligned by y position: each
    overflow page goes to the main page whose rows line up with its flags, keeping page order
    (a monotonic best fit). Page order (k-th overflow page -> k-th main page) only breaks ties,
    so a blank overflow page that Excel left out does not shift every later page."""
    mains = [p["index"] for p in pages if p["kind"] == "M"]
    overs = [p["index"] for p in pages if p["kind"] == "O"]
    flags_on = dict((p["index"], [ln for ln in p["lines"] if ln.kind in ("flag", "tag")])
                    for p in pages if p["kind"] == "O")
    flagged = [o for o in overs if flags_on[o]]
    mapping = {}
    if not mains or not flagged:
        return mapping
    last_main = max(mains)
    if any(o < last_main for o in flagged):
        for o in flagged:
            prev = [m for m in mains if m < o]
            if prev:
                mapping[o] = prev[-1]
        return mapping
    trailing = [o for o in overs if o > last_main]
    order_guess = dict((o, mains[k]) for k, o in enumerate(trailing) if k < len(mains))
    if len(flagged) > len(mains):
        warnings.append("More overflow pages with Rookie flags (%d) than main pages (%d); extra overflow "
                        "pages ignored" % (len(flagged), len(mains)))
        for o in flagged:
            if o in order_guess:
                mapping[o] = order_guess[o]
        return mapping
    # Monotonic best fit. Primary: flags that line up with a row on the chosen main page.
    # Tie-break: the first page follows page order, later pages keep the page distance to the
    # previous overflow page (so after a left-out blank page the shift carries on consistently).
    nf, nm = len(flagged), len(mains)
    hits = [[_flag_match_count(flags_on[o], rows_by_page.get(m, [])) for m in mains] for o in flagged]
    NEG = None
    best = [[NEG] * nm for _ in range(nf)]
    back = [[None] * nm for _ in range(nf)]
    for j in range(nm - nf + 1):
        best[0][j] = (hits[0][j], 1 if order_guess.get(flagged[0]) == mains[j] else 0)
    for i in range(1, nf):
        gap_o = flagged[i] - flagged[i - 1]
        for j in range(i, nm - (nf - i) + 1):
            for jp in range(i - 1, j):
                if best[i - 1][jp] is NEG:
                    continue
                keep = 1 if mains[j] - mains[jp] == gap_o else 0
                cand = (best[i - 1][jp][0] + hits[i][j], best[i - 1][jp][1] + keep)
                if best[i][j] is NEG or cand > best[i][j]:
                    best[i][j] = cand
                    back[i][j] = jp
    ends = [jj for jj in range(nm) if best[nf - 1][jj] is not NEG]
    if not ends:
        return dict((o, order_guess[o]) for o in flagged if o in order_guess)
    j = max(ends, key=lambda jj: best[nf - 1][jj])
    for i in range(nf - 1, -1, -1):
        mapping[flagged[i]] = mains[j]
        j = back[i][j]
    moved = [o for o in flagged if order_guess.get(o) != mapping[o]]
    if moved:
        warnings.append("Rookie overflow pages %s were matched to main pages by row position, not page order "
                        "(a blank overflow page is probably missing); check the Rookie flags"
                        % ", ".join("%d->%d" % (o + 1, mapping[o] + 1) for o in moved))
    return mapping


# ------------------------------------------------------------------ columns

def _line_intervals(ln, exclude_from=None):
    """Merged x-intervals covered by a line's characters (spaces included)."""
    chars = ln.chars
    if exclude_from is not None:
        chars = [c for c in chars if c["x0"] < exclude_from - 0.5]
    iv = []
    for c in chars:
        x0, x1 = float(c["x0"]), float(c["x1"])
        if x1 <= x0:
            continue
        # characters of one word/cell touch (gaps well under 0.3pt); column gutters are wider
        if iv and x0 <= iv[-1][1] + 0.3:
            iv[-1][1] = max(iv[-1][1], x1)
        else:
            iv.append([x0, x1])
    # If the PDF has no explicit space characters, bridge word gaps that are clearly spaces.
    if chars and not any(c["text"] == " " for c in chars):
        size = float(chars[0].get("size") or 8.0)
        merged = []
        for a in iv:
            if merged and a[0] - merged[-1][1] < 0.22 * size:
                merged[-1][1] = max(merged[-1][1], a[1])
            else:
                merged.append(a)
        iv = merged
    return iv


def find_columns(row_lines):
    """Find column boundaries as vertical gutters no row character crosses.

    Returns a sorted list of boundary x positions."""
    if not row_lines:
        return []
    per_line = []
    for ln in row_lines:
        excl = ln.words[-ln.flag]["x0"] if ln.flag else None
        iv = _line_intervals(ln, excl)
        if iv:
            per_line.append(iv)
    n = len(per_line)
    if n == 0:
        return []
    events = []
    for iv in per_line:
        for a, b in iv:
            events.append((a, 1))
            events.append((b, -1))
    events.sort(key=lambda e: (e[0], e[1]))
    lo = min(e[0] for e in events)
    hi = max(e[0] for e in events)
    # A few rows may cross a gutter (a long name printed over the empty team cell, a merged
    # cell); allow ~2% of rows, at least one once there are 20 rows.
    allow = max(1, int(0.02 * n)) if n >= 20 else 0
    # sweep to find maximal gaps where coverage <= allow
    gaps = []
    cover = 0
    gap_start = None
    for x, d in events:
        prev = cover
        cover += d
        if prev > allow and cover <= allow:
            gap_start = x
        elif prev <= allow and cover > allow and gap_start is not None:
            if x - gap_start > 0.6:
                gaps.append((gap_start, x))
            gap_start = None
    boundaries = []
    for g0, g1 in gaps:
        if g0 <= lo or g1 >= hi:
            continue
        # Just left of where the right-hand column starts (columns are left-aligned), so a
        # long left-hand cell that runs into the gutter stays in its own column.
        mid = max((g0 + g1) / 2.0, g1 - 0.5)
        both = 0
        for iv in per_line:
            left = any(b <= g0 + 0.01 for a, b in iv)
            right = any(a >= g1 - 0.01 for a, b in iv)
            if left and right:
                both += 1
        if both >= max(2, 0.15 * n):
            boundaries.append(mid)
    return sorted(boundaries)


def _runs(ln, boundaries=(), exclude_from=None):
    """Split a line into text runs (words) in content-stream order.

    A run ends at a space, at any visible gap between letters (more than 0.12 em; letters of a
    word touch), or where the text jumps backwards (an overflowing cell drawn under the next
    cell). Each run is later assigned whole to the column holding its start, so a name that
    overflows into the next column is never split mid-word."""
    stream = sorted(ln.chars, key=lambda c: c.get("_i", 0))
    runs = []
    cur = None
    space_before = False
    for c in stream:
        x0, x1 = float(c["x0"]), float(c["x1"])
        if exclude_from is not None and x0 >= exclude_from:
            continue
        if not c["text"].strip():
            if cur is not None:
                runs.append(cur)
                cur = None
            space_before = True
            continue
        size = float(c.get("size") or 8.0)
        brk = cur is None
        if cur is not None:
            if x0 < cur["last_x0"] or x0 - cur["x1"] > 0.12 * size:
                brk = True
        if brk:
            if cur is not None:
                runs.append(cur)
            cur = {"text": "", "x0": x0, "x1": x1, "last_x0": x0, "size": size, "space": space_before}
            space_before = False
        cur["text"] += c["text"]
        cur["x1"] = max(cur["x1"], x1)
        cur["last_x0"] = x0
    if cur is not None:
        runs.append(cur)
    return runs


def _cell_texts(ln, boundaries):
    cols = [[] for _ in range(len(boundaries) + 1)]
    excl = ln.words[-ln.flag]["x0"] - 0.5 if ln.flag else None
    for r in _runs(ln, boundaries, excl):
        k = 0
        while k < len(boundaries) and r["x0"] > boundaries[k]:
            k += 1
        cols[k].append(r)
    out = []
    for runs in cols:
        runs.sort(key=lambda r: r["x0"])
        s = []
        prev = None
        for r in runs:
            if prev is not None and (r["space"] or r["x0"] - prev["x1"] > 0.25 * r["size"]):
                s.append(" ")
            s.append(r["text"])
            prev = r
        out.append(clean_space("".join(s)))
    return out


def merge_code_columns(row_lines, boundaries):
    """Merge neighbouring columns that never hold text on the same line and are both code-like.

    Excel prints numbers right-aligned and text left-aligned, so a code column holding both
    ``12`` and ``RR-1`` shows up as two columns with a gutter between them."""
    boundaries = list(boundaries)
    changed = True
    while changed and boundaries:
        changed = False
        texts = [_cell_texts(ln, boundaries) for ln in row_lines]
        for k in range(len(boundaries)):
            a = [t[k] for t in texts]
            b = [t[k + 1] for t in texts]
            either = sum(1 for x, y in zip(a, b) if x or y)
            both = sum(1 for x, y in zip(a, b) if x and y)
            if not either or both > 0.01 * either:
                continue
            na = [x for x in a if x]
            nb = [y for y in b if y]
            if not na or not nb:
                continue
            ca = sum(1 for x in na if is_code_like(x)) >= 0.6 * len(na)
            cb = sum(1 for y in nb if is_code_like(y)) >= 0.6 * len(nb)
            if ca and cb:
                del boundaries[k]
                changed = True
                break
    return boundaries


def assign_roles(row_lines, boundaries):
    """Decide which column is code / name / team / tag. Returns (roles, cell texts).

    A trailing, sparsely filled column holding a small vocabulary ("Rookie", "Future Stars",
    "Combo Card", ...) is the flag column ("tag"), never part of the team."""
    ncols = len(boundaries) + 1
    texts = [_cell_texts(ln, boundaries) for ln in row_lines]
    filled = [sum(1 for t in texts if t[k]) for k in range(ncols)]
    cols = [k for k in range(ncols) if filled[k] > 0]
    roles = {"code": None, "name": None, "team": [], "tag": None}
    if not cols:
        return roles, texts
    first = cols[0]
    nonempty = [t[first] for t in texts if t[first]]
    codeish = sum(1 for s in nonempty if is_code_like(s))
    rest = cols
    if len(cols) >= 2 and codeish >= 0.5 * len(nonempty):
        roles["code"] = first
        rest = cols[1:]
    if len(rest) >= 3:
        last = rest[-1]
        values = [t[last] for t in texts if t[last]]
        distinct = set(v.upper() for v in values)
        if len(values) < 0.6 * len(texts) and len(distinct) <= max(5, 0.1 * len(values)):
            roles["tag"] = last
            rest = rest[:-1]
    if rest:
        roles["name"] = rest[0]
        roles["team"] = rest[1:]
    return roles, texts


GLUED_RE = re.compile(r"^([A-Z]{0,6}-?\d+[A-Za-z]?|\d+)\s+(.+)$")


def split_row(cells, roles):
    code = cells[roles["code"]] if roles["code"] is not None else ""
    name = cells[roles["name"]] if roles["name"] is not None else ""
    team = " ".join(cells[k] for k in roles["team"] if cells[k])
    tag = cells[roles["tag"]] if roles.get("tag") is not None else ""
    if roles["code"] is None and name:
        m = GLUED_RE.match(name)
        if m and any(ch.isdigit() for ch in m.group(1)):
            code, name = m.group(1), m.group(2)
    return code, name, team, tag


def _row_pitch(rows):
    diffs = []
    for a, b in zip(rows, rows[1:]):
        if a.page == b.page and b.top > a.top:
            diffs.append(b.top - a.top)
    if not diffs:
        return 12.0
    diffs.sort()
    return diffs[len(diffs) // 2]


def _resolve_merged_codes(rows, pitch, warnings, section):
    """Handle a code printed once, vertically centred over two rows.

    Such a code shows up as its own line half a row below the first row and half a row above
    the next, while those rows carry no code. Either it is a multi-player card (the usual
    case: every card of the section looks like this), or a single player whose name wrapped
    onto two lines with code and team centred (the section's other cards are one-row cards)."""
    def merged_at(i):
        r = rows[i]
        if not (r["code"] and not r["name"] and 0 < i < len(rows) - 1):
            return False
        prev, nxt = rows[i - 1], rows[i + 1]
        return (not prev["code"] and not nxt["code"] and prev["name"] and nxt["name"]
                and prev["page"] == r["page"] == nxt["page"]
                and r["top"] - prev["top"] < 0.75 * pitch
                and nxt["top"] - r["top"] < 0.75 * pitch)

    merged = [i for i in range(len(rows)) if merged_at(i)]
    in_merge = set()
    for i in merged:
        in_merge.update((i - 1, i, i + 1))
    singles = sum(1 for i, r in enumerate(rows) if i not in in_merge and r["code"] and r["name"])
    wrapped_names = singles > len(merged)
    out = []
    i = 0
    n = len(rows)
    while i < n:
        r = rows[i]
        if (i in merged and out and out[-1]["top"] == rows[i - 1]["top"] and not out[-1]["code"]):
            prev, nxt = out[-1], dict(rows[i + 1])
            if wrapped_names and not prev["team"] and not nxt["team"]:
                prev["name"] = clean_space(prev["name"] + " " + nxt["name"])
                prev["code"] = r["code"]
                prev["team"] = r["team"]
                prev["rookie"] = prev["rookie"] or r["rookie"] or nxt["rookie"]
                prev["tags"] = prev.get("tags", []) + r.get("tags", []) + nxt.get("tags", [])
                i += 2
                continue
            prev["code"] = r["code"]
            nxt["code"] = r["code"]
            if r["team"]:
                if not prev["team"] and not nxt["team"]:
                    # one team cell centred over both players
                    prev["team"] = nxt["team"] = r["team"]
                else:
                    # e.g. the national team of a dual card, printed on the code line
                    prev["tags"] = prev.get("tags", []) + [r["team"]]
            prev["tags"] = prev.get("tags", []) + [t for t in r.get("tags", []) if t not in prev.get("tags", [])]
            prev["rookie"] = prev["rookie"] or r["rookie"]
            out.append(nxt)
            i += 2
            continue
        out.append(dict(r))
        i += 1
    return _fill_continuation_codes(out, warnings, section)


def _fill_continuation_codes(rows, warnings=None, section=""):
    """Multi-player cards that print the code on the first player's row only.

    Applied when the section starts with a coded row, has at least two coded rows, most coded
    rows are followed by uncoded ones (e.g. DUAL / TRIPLE autographs), and the resulting cards
    are small; uncoded rows then join the card above."""
    if not rows or not rows[0]["code"]:
        return rows
    coded = [i for i, r in enumerate(rows) if r["code"]]
    uncoded = len(rows) - len(coded)
    if not uncoded or len(coded) < 2:
        return rows
    followed = sum(1 for i in coded if i + 1 < len(rows) and not rows[i + 1]["code"])
    if followed < 0.6 * len(coded):
        return rows
    sizes = [b - a for a, b in zip(coded, coded[1:] + [len(rows)])]
    if max(sizes) > MAX_CARD_PLAYERS + 2:
        if warnings is not None:
            warnings.append("Section %r: rows without a code were not joined to the card above "
                            "(a card would get %d players)" % (section, max(sizes)))
        return rows
    current = None
    for r in rows:
        if r["code"]:
            current = r["code"]
        elif current:
            r["code"] = current
    return rows


# ------------------------------------------------------------------ main entry

def _section_base_name(raw):
    """Header text without a trailing "(CONTINUED)" marker."""
    return clean_space(CONTINUED_RE.sub("", raw)) or raw


def parse_checklist(path):
    warnings = []
    try:
        pdf = pdfplumber.open(path)
    except Exception as exc:
        raise ChecklistError("cannot open checklist PDF %s: %s" % (path, exc))
    try:
        with pdf:
            pages = read_pages(pdf)
    except Exception as exc:
        raise ChecklistError("cannot read checklist PDF %s: %s" % (path, exc))
    title, disclaimer = classify_lines(pages, warnings)
    classify_pages(pages)

    # same-line trailing rookie flags
    for page in pages:
        if page["kind"] != "M":
            continue
        for ln in page["lines"]:
            if ln.kind == "row":
                ln.flag = _flag_text(ln)
                if ln.flag:
                    ln.rookie = True

    main_rows = [ln for p in pages if p["kind"] == "M" for ln in p["lines"] if ln.kind == "row"]
    if not main_rows:
        raise ChecklistError("no card rows found in checklist PDF %s (no extractable text? a scanned "
                             "PDF cannot be read)" % path)
    inline_rookies = sum(1 for ln in main_rows if ln.flag)
    # Other values in the same flag column ("Future Stars", "Combo Card"): a trailing cell that
    # starts where the inline Rookie flags start. They become card tags, never part of the team.
    flag_xs = sorted(ln.words[-ln.flag]["x0"] for ln in main_rows if ln.flag)
    if len(flag_xs) >= 2:
        fx = flag_xs[len(flag_xs) // 2]
        for ln in main_rows:
            if ln.flag:
                continue
            for j in range(1, len(ln.words)):
                w = ln.words[j]
                if abs(w["x0"] - fx) <= 3 and w["x0"] - ln.words[j - 1]["x1"] > 2:
                    ln.flag = len(ln.words) - j
                    ln.tag = clean_space(" ".join(x["text"] for x in ln.words[j:]))
                    break
    boundaries = merge_code_columns(main_rows, find_columns(main_rows))
    roles, texts = assign_roles(main_rows, boundaries)
    for ln, cells in zip(main_rows, texts):
        ln.cells = cells
    if not roles["team"]:
        marked = sum(1 for ln in main_rows if re.search(u"[®™]", ln.text))
        if marked >= 0.5 * len(main_rows):
            warnings.append("No team column found although most rows carry a team (®/™); a cell that "
                            "overflows into the team column may have hidden the column gap. Check names.")

    # overflow rookie flags
    rows_by_page = {}
    for ln in main_rows:
        rows_by_page.setdefault(ln.page, []).append(ln)
    mapping = map_overflow(pages, rows_by_page, warnings)
    overflow_flags = 0
    overflow_mapped = 0
    for page in pages:
        if page["kind"] != "O":
            continue
        flags = [ln for ln in page["lines"] if ln.kind in ("flag", "tag")]
        if not flags:
            continue
        target = mapping.get(page["index"])
        overflow_flags += sum(1 for fl in flags if fl.kind == "flag")
        if target is None:
            warnings.append("Rookie flags on page %d could not be mapped to a checklist page"
                            % (page["index"] + 1))
            continue
        candidates = rows_by_page.get(target, [])
        for fl in flags:
            best = None
            for ln in candidates:
                d = abs(ln.top - fl.top)
                if d <= 2.5 and (best is None or d < abs(best.top - fl.top)):
                    best = ln
            if best is None:
                warnings.append("%s on page %d (y=%.1f) has no matching row on page %d"
                                % ("Rookie flag" if fl.kind == "flag" else "Flag-column value %r" % fl.text,
                                   page["index"] + 1, fl.top, target + 1))
                continue
            if fl.kind == "tag":
                best.tag = fl.text if not best.tag else best.tag + " " + fl.text
                continue
            if best.rookie:
                warnings.append("Row %r on page %d received two Rookie flags" % (best.text, target + 1))
            best.rookie = True
            overflow_mapped += 1
    # Flags on main pages that sit on their own line (no row) are reported.
    for page in pages:
        if page["kind"] == "M":
            for ln in page["lines"]:
                if ln.kind == "flag":
                    warnings.append("Stray Rookie flag on page %d (y=%.1f)" % (page["index"] + 1, ln.top))

    # ---- assemble groups / sections / cards
    seq = [ln for p in pages if p["kind"] == "M" for ln in p["lines"] if ln.kind in ("header", "row", "note")]
    if not any(ln.kind == "header" for ln in seq):
        warnings.append("No section headers found: every card is in one section. Check the checklist PDF.")
    sections = []
    group = None
    current = None

    def new_section(raw, grp, ln):
        sec = OrderedDict()
        sec["rawName"] = raw
        sec["group"] = grp or ""
        sec["page"] = ln.page + 1
        sec["cards"] = []
        sec["rowCount"] = 0
        sec["notes"] = []
        sec["_rows"] = []
        sections.append(sec)
        return sec

    for idx, ln in enumerate(seq):
        if ln.kind == "note":
            if current is not None:
                current["notes"].append(ln.text)
            else:
                warnings.append("Note outside a section on page %d: %r" % (ln.page + 1, ln.text))
            continue
        if ln.kind == "header":
            nxt = None
            for later in seq[idx + 1:]:
                if later.kind != "note":
                    nxt = later
                    break
            raw = _section_base_name(clean_space(normalize_quotes(ln.text)))
            nxt_raw = None
            if nxt is not None and nxt.kind == "header":
                nxt_raw = _section_base_name(clean_space(normalize_quotes(nxt.text)))
            if is_group_vocab(raw):
                if current is not None and raw == group and (
                        (nxt is not None and nxt.kind == "row" and current["rawName"] == raw)
                        or (nxt_raw is not None and nxt_raw == current["rawName"])):
                    continue   # group (+ section) header repeated at the top of a page
                group = raw
                if nxt is not None and nxt.kind == "row":
                    current = new_section(raw, group, ln)
                else:
                    current = None
                continue
            if current is not None and current["rawName"] == raw:
                continue       # section header repeated after a page break, or "... (CONTINUED)"
            if nxt_raw is not None:
                if group is not None and is_group_vocab(group):
                    # A section whose cards are not listed (yet): keep it, keep the group.
                    current = new_section(raw, group, ln)
                    current["notes"].append("No cards listed in the checklist")
                    continue
                warnings.append("Header %r (page %d) is followed directly by another header; "
                                "treated as a group header" % (raw, ln.page + 1))
                group = raw
                current = None
                continue
            current = new_section(raw, group, ln)
            continue
        # card row
        code, name, team, tag = split_row(ln.cells, roles)
        rookie = bool(ln.rookie)
        tags = []
        for t in (ln.tag, tag):
            if not t:
                continue
            if t.upper() in ROOKIE_FLAGS:
                rookie = True
            elif t not in tags:
                tags.append(t)
        if current is None:
            raw = group or "CHECKLIST"
            warnings.append("Card rows before any section header on page %d; put in %r" % (ln.page + 1, raw))
            current = new_section(raw, group, ln)
        if not code and not name and not team:
            warnings.append("Unreadable row on page %d: %r" % (ln.page + 1, ln.text))
            continue
        current["_rows"].append({
            "code": code, "name": name, "team": team, "rookie": rookie, "tags": tags,
            "page": ln.page, "top": ln.top, "text": ln.text})

    pitch = _row_pitch(main_rows)
    for sec in sections:
        rows = _resolve_merged_codes(sec.pop("_rows", []), pitch, warnings, sec["rawName"])
        sec["rowCount"] = len(rows)
        cards = sec["cards"]
        for r in rows:
            player = OrderedDict([("name", clean_name(r["name"])), ("team", clean_team(r["team"])),
                                  ("rookie", r["rookie"])])
            last = cards[-1] if cards else None
            if r["code"] and last is not None and last["code"] == r["code"]:
                if player["name"] and player["name"] in [p["name"] for p in last["players"]]:
                    warnings.append("Section %r: card %s lists %r twice in a row; kept as two cards"
                                    % (sec["rawName"], r["code"], player["name"]))
                else:
                    last["players"].append(player)
                    last["rookie"] = last["rookie"] or player["rookie"]
                    for t in r.get("tags", []):
                        last.setdefault("tags", [])
                        if t not in last["tags"]:
                            last["tags"].append(t)
                    continue
            card = OrderedDict([("code", r["code"]), ("rookie", player["rookie"]), ("players", [player])])
            if r.get("tags"):
                card["tags"] = list(r["tags"])
            cards.append(card)
        for c in cards:
            if len(c["players"]) > MAX_CARD_PLAYERS:
                warnings.append("Section %r: card %s has %d players; check that rows were not joined by mistake"
                                % (sec["rawName"], c["code"] or "(no code)", len(c["players"])))

    for sec in sections:
        if not sec["cards"]:
            warnings.append("Section %r has no cards" % sec["rawName"])

    stats = OrderedDict()
    stats["pages"] = len(pages)
    stats["mainPages"] = sum(1 for p in pages if p["kind"] == "M")
    stats["overflowPages"] = sum(1 for p in pages if p["kind"] == "O")
    stats["overflowPagesMapped"] = len(mapping)
    stats["rows"] = len(main_rows)
    stats["rookieFlagsInline"] = inline_rookies
    stats["rookieFlagsOverflow"] = overflow_flags
    stats["rookieFlagsOverflowMapped"] = overflow_mapped
    debug = {
        "boundaries": [round(b, 1) for b in boundaries],
        "roles": roles,
        "pageKinds": "".join(p["kind"] for p in pages),
        "overflowMap": dict((k + 1, v + 1) for k, v in sorted(mapping.items())),
        "pages": pages,
    }
    return {
        "title": title,
        "disclaimer": disclaimer,
        "sections": sections,
        "warnings": warnings,
        "stats": stats,
        "debug": debug,
    }
