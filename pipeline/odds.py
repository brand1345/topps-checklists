"""Odds PDF -> formats + rows.

The odds sheet is a landscape table: a name column followed by one column per product
format (Hobby, Jumbo, ...). Values are pack odds such as ``1:341`` or ``-``.

Columns are located from the data itself: every data line ends with a run of value tokens,
and the x positions of those tokens cluster into one anchor per format (right edges when the
sheet right-aligns numbers, left edges otherwise). Header words are then assigned to the
format whose zone they fall into.
"""
from __future__ import annotations

import re
from collections import OrderedDict

import pdfplumber

from .names import clean_space, has_lower, normalize_quotes, slugify, smart_title

LINE_TOL = 2.0
VALUE_RE = re.compile(r"^(1:[\d,\.]+|\d*\.\d+|-|–|—|N/A|n/a)$")
NOT_AVAILABLE = ("-", "–", "—", "N/A", "n/a")
DISCLAIMER_RE = re.compile(r"checklists?\b.{0,40}\bprovided\b", re.I)
FORMAT_CODE_RE = re.compile(r"^\s*(\d{3,})\s*-\s*")
YEAR_TOKEN_RE = re.compile(r"\b(?:19|20)\d\d(?:[-/]\d{2,4})?\b")
MAX_DISCLAIMER_LINES = 6
PARALLEL_SUFFIX_RE = re.compile(r"\s+PARALLELS?$", re.I)


class OddsError(Exception):
    pass


def parse_value(raw):
    """Return None for '-' (not in format) or {'raw', 'n'[, 'error']}."""
    raw = clean_space(raw)
    if raw in NOT_AVAILABLE or raw == "":
        return None
    out = OrderedDict([("raw", raw), ("n", None)])
    m = re.match(r"^1:([\d,\.]+)$", raw)
    if m:
        num = m.group(1)
        if re.match(r"^\d{1,3}(,\d{3})*$", num) or re.match(r"^\d+$", num):
            out["n"] = int(num.replace(",", ""))
        elif re.match(r"^[\d,]+$", num):
            out["n"] = int(num.replace(",", ""))
            out["error"] = "malformed number in source"
        else:
            out["error"] = "unreadable value in source"
        return out
    out["error"] = "unreadable value in source"
    return out


def _lines(page_index, words):
    lines = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(w["top"] - lines[-1][-1]["top"]) <= LINE_TOL:
            lines[-1].append(w)
        else:
            lines.append([w])
    out = []
    for ws in lines:
        ws.sort(key=lambda w: w["x0"])
        # Re-join values that pdfplumber split, e.g. "1" + ":15,000".
        merged = []
        for w in ws:
            if (merged and w["text"].startswith(":") and re.match(r"^\d+$", merged[-1]["text"])
                    and w["x0"] - merged[-1]["x1"] < 2.0):
                prev = dict(merged[-1])
                prev["text"] = prev["text"] + w["text"]
                prev["x1"] = w["x1"]
                merged[-1] = prev
            else:
                merged.append(w)
        out.append({"page": page_index, "top": min(w["top"] for w in merged), "words": merged,
                    "text": clean_space(" ".join(w["text"] for w in merged))})
    return out


def _trailing_values(words):
    k = len(words)
    while k > 0 and VALUE_RE.match(words[k - 1]["text"]):
        k -= 1
    # a line made only of "-" tokens etc. still needs a name, unless all are 1:x values
    return k


def _cluster_words(words, key, tol=3.0):
    """Group words whose `key` edge lies within `tol` of the previous one."""
    out = []
    for w in sorted(words, key=lambda w: w[key]):
        if out and w[key] - out[-1][-1][key] <= tol:
            out[-1].append(w)
        else:
            out.append([w])
    return out


def _is_number(text):
    return text not in NOT_AVAILABLE


def _cluster(xs, tol=3.0):
    xs = sorted(xs)
    clusters = []
    for x in xs:
        if clusters and x - clusters[-1][-1] <= tol:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    return clusters


def format_label(raw):
    """'6625 - MLB-CHROME 2026 HOBBY' -> ('HOBBY', '6625'): drop the product code and the
    product name / year that precede the format name."""
    s = clean_space(raw)
    m = FORMAT_CODE_RE.match(s)
    code = None
    if m:
        code = m.group(1)
        rest = s[m.end():].strip()
        years = list(YEAR_TOKEN_RE.finditer(rest))
        if years and rest[years[-1].end():].strip():
            label = rest[years[-1].end():].strip()
        else:
            parts = rest.split(" ", 1)
            label = parts[1].strip() if len(parts) > 1 else rest
        if label:
            s = label
    s = re.sub(r"\s+pack\s+rates?$", "", s, flags=re.I)
    s = re.sub(r"\s+rates?$", "", s, flags=re.I)
    s = re.sub(r"^odds\s*", "", s, flags=re.I)
    s = s.strip(" ()")
    s = re.sub(r"[()]", "", s).strip()
    return s or clean_space(raw), code


def _has_values(ln):
    k = _trailing_values(ln["words"])
    return k < len(ln["words"]) and any(w["text"].startswith("1:") or "." in w["text"]
                                         for w in ln["words"][k:])


def parse_odds(path):
    warnings = []
    try:
        pdf = pdfplumber.open(path)
    except Exception as exc:
        raise OddsError("cannot open odds PDF %s: %s" % (path, exc))
    pages = []
    try:
        with pdf:
            for pi, page in enumerate(pdf.pages):
                try:
                    words = page.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False,
                                               use_text_flow=False, x_tolerance=1.5)
                except Exception:  # pragma: no cover
                    words = []
                width = float(page.width)
                words = [w for w in words if w["x1"] > 0 and w["x0"] < width]
                pages.append(_lines(pi, words) if words else [])
    except OddsError:
        raise
    except Exception as exc:
        raise OddsError("cannot read odds PDF %s: %s" % (path, exc))

    title = None
    disclaimer_parts = []
    # --- pass 1: mark disclaimer lines, data lines
    for lines in pages:
        in_disc = False
        disc_lines = 0
        for ln in lines:
            ln["kind"] = None
            text = ln["text"]
            if in_disc and (_has_values(ln) or disc_lines >= MAX_DISCLAIMER_LINES):
                # A disclaimer that never ends in "vary." / "." / "**": stop at the first odds row.
                in_disc = False
                warnings.append("Disclaimer on page %d has no clear end; it was cut off after %d lines"
                                % (ln["page"] + 1, disc_lines))
            if (DISCLAIMER_RE.search(text) and not _has_values(ln)) or in_disc:
                ln["kind"] = "disclaimer"
                disc_lines += 1
                if not in_disc:
                    pre, sep, post = text.partition("**")
                    if sep and DISCLAIMER_RE.search(post) and title is None and pre.strip():
                        title = pre.strip()
                        text = post
                    in_disc = True
                if len(disclaimer_parts) < 6 and len(pages) and lines is pages[0]:
                    disclaimer_parts.append(text)
                if re.search(r"(variation|vary)[.,]?\**\s*$", text, re.I) or text.endswith("**") \
                        or text.endswith("."):
                    in_disc = False
                continue
            k = _trailing_values(ln["words"])
            if _has_values(ln):
                ln["kind"] = "data"
                ln["k"] = k
            elif k < len(ln["words"]) and k > 0:
                # only "-" / "N/A" values: still a data row if it has a name
                if all(w["text"] in NOT_AVAILABLE for w in ln["words"][k:]):
                    ln["kind"] = "data?"
                    ln["k"] = k
    # --- columns from value tokens: anchors come from numbers; "-" cells may be centred while
    # numbers are right-aligned, so they never create a column on their own (see below)
    value_words = []
    for lines in pages:
        for ln in lines:
            if ln["kind"] == "data":
                value_words.extend(ln["words"][ln["k"]:])
    num_words = [w for w in value_words if _is_number(w["text"])]
    if not num_words:
        raise OddsError("no odds values found in %s" % path)
    right = _cluster_words(num_words, "x1")
    left = _cluster_words(num_words, "x0")
    align = "right" if len(right) <= len(left) else "left"
    edge = "x1" if align == "right" else "x0"
    clusters = right if align == "right" else left
    support = [len(c) for c in clusters]
    clusters = [c for c in clusters if len(c) >= max(2, 0.02 * max(support))] or clusters
    anchors = [sum(w[edge] for w in c) / len(c) for c in clusters]
    spans = [(min(w["x0"] for w in c), max(w["x1"] for w in c)) for c in clusters]
    nf = len(anchors)

    def zone_of(x0, x1):
        """Index of the format column a word belongs to."""
        if align == "right":
            cx = (x0 + x1) / 2.0
            for i, a in enumerate(anchors):
                if cx <= a + 3:
                    return i
            return nf - 1
        cx = (x0 + x1) / 2.0
        idx = 0
        for i, a in enumerate(anchors):
            if cx >= a - 3:
                idx = i
        return idx

    # first value column's left limit (to separate names from values)
    min_val_x0 = min(w["x0"] for w in value_words)
    # "data?" lines (only dashes): confirm by position
    for lines in pages:
        for ln in lines:
            if ln["kind"] == "data?":
                if all(w["x0"] >= min_val_x0 - 2 for w in ln["words"][ln["k"]:]):
                    ln["kind"] = "data"
                else:
                    ln["kind"] = None

    # --- header: lines before the first data line on each page (excluding disclaimer)
    header_lines = []
    for lines in pages:
        first_data = next((i for i, ln in enumerate(lines) if ln["kind"] == "data"), None)
        if first_data is None:
            continue
        for ln in lines[:first_data]:
            if ln["kind"] is None:
                ln["kind"] = "header"
                if lines is pages[0] or not header_lines:
                    header_lines.append(ln)
    widths = sorted(b - a for a, b in zip(anchors, anchors[1:]))
    col_w = widths[len(widths) // 2] if widths else max(150.0, anchors[0] - min_val_x0 + 60)

    # Columns that hold only "-": add one only where a format label sits above the dashes.
    dash_words = [w for lines in pages for ln in lines if ln["kind"] == "data"
                  for w in ln["words"][ln["k"]:] if not _is_number(w["text"])]
    head_words = [w for ln in header_lines for w in ln["words"]]
    added = False
    for c in _cluster_words(dash_words, "x0", tol=6.0):
        cx = sum((w["x0"] + w["x1"]) / 2.0 for w in c) / len(c)
        if any(a0 - 0.35 * col_w <= cx <= a1 + 0.35 * col_w for a0, a1 in spans):
            continue
        above = [w for w in head_words if abs((w["x0"] + w["x1"]) / 2.0 - cx) <= 0.5 * col_w]
        if not above:
            continue
        if align == "right":
            a = max([w["x1"] for w in c] + [w["x1"] for w in above])
        else:
            a = min([w["x0"] for w in c] + [w["x0"] for w in above])
        anchors.append(a)
        spans.append((min(w["x0"] for w in c + above), max(w["x1"] for w in c + above)))
        added = True
    if added:
        order = sorted(range(len(anchors)), key=lambda i: anchors[i])
        anchors = [anchors[i] for i in order]
        spans = [spans[i] for i in order]
        nf = len(anchors)

    label_words = []
    fmt_words = [[] for _ in range(nf)]
    for ln in header_lines:
        for w in ln["words"]:
            cx = (w["x0"] + w["x1"]) / 2.0
            if align == "right":
                is_label = cx <= anchors[0] - col_w
            else:
                is_label = cx < anchors[0] - 10
            if is_label:
                label_words.append(w)
            else:
                fmt_words[zone_of(w["x0"], w["x1"])].append(w)
    formats = []
    used = set()
    any_lower = any(has_lower(w["text"]) for ws in fmt_words for w in ws)
    for i in range(nf):
        raw = clean_space(" ".join(w["text"] for w in fmt_words[i])) or ("Format %d" % (i + 1))
        label, code = format_label(raw)
        if not any_lower:
            label = smart_title(label)
        fid = slugify(label)
        base = fid
        n = 2
        while fid in used:
            fid = "%s-%d" % (base, n)
            n += 1
        used.add(fid)
        formats.append(OrderedDict([("id", fid), ("label", label), ("raw", raw), ("code", code)]))
    first_label = clean_space(" ".join(w["text"] for w in label_words)) or None

    # --- rows. Value-less lines are parts of names: the wrapped end of the row above (just below
    # it, not left of its name), or the start of a row whose values sit centred on the next line.
    tops = []
    for lines in pages:
        data_tops = [ln["top"] for ln in lines if ln["kind"] == "data"]
        tops.extend(b - a for a, b in zip(data_tops, data_tops[1:]) if b > a)
    tops.sort()
    pitch = tops[len(tops) // 2] if tops else 12.0
    name_x0s = [ln["words"][0]["x0"] for lines in pages for ln in lines
                if ln["kind"] == "data" and ln["k"] > 0]
    name_x0 = min(name_x0s) if name_x0s else 0.0
    rows = []
    for lines in pages:
        prev = None
        prefix = []
        for idx, ln in enumerate(lines):
            kind = ln["kind"]
            if kind == "data":
                name_words = ln["words"][:ln["k"]]
                vals = [None] * nf
                raws = [None] * nf
                for w in ln["words"][ln["k"]:]:
                    z = zone_of(w["x0"], w["x1"])
                    if raws[z] is not None:
                        warnings.append("Two values in one column for %r" % ln["text"])
                    raws[z] = w["text"]
                name = clean_space(" ".join(w["text"] for w in name_words))
                if prefix:
                    name = clean_space(" ".join(p["text"] for p in prefix) + " " + name)
                    prefix = []
                missing = [formats[i]["id"] for i in range(nf) if raws[i] is None]
                if missing and len(missing) < nf:
                    warnings.append("Row %r has no value for %s (treated as not available)"
                                    % (name, ", ".join(missing)))
                row = OrderedDict()
                row["rawName"] = name
                row["values"] = raws
                row["page"] = ln["page"] + 1
                row["_last_top"] = ln["top"]
                rows.append(row)
                prev = row
            elif kind is None:
                if not ln["words"]:
                    continue
                x0 = ln["words"][0]["x0"]
                if x0 >= min_val_x0 or x0 < name_x0 - 2:
                    if ln["text"]:
                        warnings.append("Ignored odds line on page %d: %r" % (ln["page"] + 1, ln["text"]))
                    continue
                nxt = next((l2 for l2 in lines[idx + 1:] if l2["kind"] is not None), None)
                if (nxt is not None and nxt["kind"] == "data" and nxt["k"] == 0
                        and 0 < nxt["top"] - ln["top"] <= 0.75 * pitch):
                    prefix.append(ln)   # name printed above its vertically centred values
                elif prev is not None and 0 < ln["top"] - prev["_last_top"] <= 1.5 * pitch:
                    prev["rawName"] = clean_space(prev["rawName"] + " " + ln["text"])
                    prev["_last_top"] = ln["top"]
                    prev.setdefault("wrapped", True)
                else:
                    warnings.append("Ignored odds line on page %d: %r" % (ln["page"] + 1, ln["text"]))
            elif kind == "header":
                prev = None
        for p in prefix:
            warnings.append("Ignored odds line on page %d: %r" % (p["page"] + 1, p["text"]))
    for row in rows:
        row.pop("_last_top", None)
        # rawName keeps the source text (curly apostrophes included); `name` is for matching
        name = PARALLEL_SUFFIX_RE.sub("", normalize_quotes(row["rawName"]))
        row["name"] = name
        row["odds"] = OrderedDict((formats[i]["id"], parse_value(row["values"][i]) if row["values"][i] else None)
                                  for i in range(nf))
        if not row["rawName"]:
            warnings.append("Odds row without a name on page %d" % row["page"])
    disclaimer = clean_space(" ".join(disclaimer_parts)).replace("**", "").strip() or None
    return {
        "title": title,
        "disclaimer": disclaimer,
        "label": first_label,
        "align": align,
        "formats": formats,
        "rows": rows,
        "warnings": warnings,
    }
