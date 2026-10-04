"""Tiny PDF writer for layout tests (standard Type1 fonts, no dependencies).

A page is a list of text items ``(x, top, text, font)`` with font ``R`` (regular), ``B`` (bold) or
``I`` (italic); items are drawn in list order, which is the PDF content-stream order.
"""
import os
import tempfile

FONTS = {"R": "Helvetica", "B": "Helvetica-Bold", "I": "Helvetica-Oblique"}
TEAMS = ["Los Angeles Dodgers\xae", "New York Yankees\xae", "Chicago Cubs\xae", "Boston Red Sox\xae"]

# Helvetica advance widths (1/1000 em) for right-aligning numbers.
_W = {"1": 556, ":": 278, ",": 278, "-": 333, "/": 278, "N": 722, "A": 667}


def text_width(text, size=8):
    return sum(_W.get(ch, 556) for ch in text) * size / 1000.0


def _esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write(path, pages, width=612, height=792, size=8):
    objs = []

    def add(b):
        objs.append(b)
        return len(objs)

    font_ids = {}
    for k, name in FONTS.items():
        font_ids[k] = add(("<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>"
                           % name).encode())
    pages_id = len(objs) + 1
    add(b"PAGES")
    page_ids = []
    for items in pages:
        ops = []
        for x, top, text, f in items:
            y = height - top - size
            ops.append("BT /F%s %d Tf %.2f %.2f Td (%s) Tj ET" % (f, size, x, y, _esc(text)))
        stream = "\n".join(ops).encode("cp1252")
        cid = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        res = " ".join("/F%s %d 0 R" % (k, v) for k, v in font_ids.items())
        pid = add(("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R "
                   "/Resources << /Font << %s >> >> >>" % (pages_id, width, height, cid, res)).encode())
        page_ids.append(pid)
    objs[pages_id - 1] = ("<< /Type /Pages /Kids [%s] /Count %d >>"
                          % (" ".join("%d 0 R" % p for p in page_ids), len(page_ids))).encode()
    cat = add(("<< /Type /Catalog /Pages %d 0 R >>" % pages_id).encode())
    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, b in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + b + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out += b"%010d 00000 n \n" % o
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, cat, xref)
    with open(path, "wb") as fh:
        fh.write(bytes(out))
    return path


def rows(prefix, n, start_top, codefmt="%s-%d", pitch=12, rookie=lambda i: False, extra=None,
         name="Player%s Name%d"):
    """Card rows: code at x=40, name at x=100, team at x=260, flag column at x=420."""
    out = []
    for i in range(1, n + 1):
        t = start_top + (i - 1) * pitch
        out.append((40, t, codefmt % (prefix, i), "R"))
        out.append((100, t, name % (prefix, i), "R"))
        out.append((260, t, TEAMS[i % 4], "R"))
        e = extra(i) if extra else None
        if e:
            out.append((420, t, e, "R"))
        elif rookie(i):
            out.append((420, t, "Rookie", "R"))
    return out


def title(top=40):
    return [(40, top, "2027 Topps Test Checklist", "B")]


def flag_page(idxs, start_top=80, pitch=12, x=40):
    return [(x, start_top + (i - 1) * pitch, "Rookie", "R") for i in idxs]


class TempDir(object):
    def __init__(self):
        self.path = tempfile.mkdtemp(prefix="tc-synth-")

    def file(self, name):
        return os.path.join(self.path, name)


# ---------------------------------------------------------------- odds sheets

ODDS_COLS = [420, 560, 720, 860]   # right edges of HOBBY / JUMBO / MEGA / BLASTER


def odds_header(top, cols=ODDS_COLS, labels=("HOBBY", "JUMBO", "MEGA", "BLASTER")):
    out = [(14, top, "Card", "R")]
    for x, lab in zip(cols, labels):
        out.append((x - text_width(lab), top, lab, "R"))
    return out


def odds_row(top, name, vals, cols=ODDS_COLS, dash_x=None):
    out = [(14, top, name, "R")] if name else []
    for x, v in zip(cols, vals):
        if v == "-" and dash_x is not None:
            out.append((x - dash_x, top, v, "R"))
        else:
            out.append((x - text_width(v), top, v, "R"))
    return out


def odds_page(body, disclaimer_end="may vary.", extra=(), pitch=11, dash_x=None, cols=ODDS_COLS,
              labels=("HOBBY", "JUMBO", "MEGA", "BLASTER")):
    it = [(8, 7, "2027 Topps Test Baseball **Checklists and odds provided by Topps reflect the intended "
                 "configuration", "R"),
          (8, 20, "of the product; actual contents and odds " + disclaimer_end, "R")]
    it += odds_header(60, cols, labels)
    t = 75
    for name, vals in body:
        it += odds_row(t, name, vals, cols, dash_x)
        t += pitch
    return it + list(extra)


ODDS_BODY = [
    ("BASE CARDS REFRACTOR", ["1:3", "1:1", "1:4", "-"]),
    ("BASE CARDS GOLD REFRACTOR", ["1:341", "1:100", "1:1,705", "-"]),
    ("HELIX", ["1:1,000", "-", "-", "-"]),
    ("HELIX SUPERFRACTOR", ["1:50,000", "-", "-", "-"]),
]
