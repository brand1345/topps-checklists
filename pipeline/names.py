"""Name helpers: display casing, slugs, team cleanup and matching tokens."""
from __future__ import annotations

import re
import unicodedata

# Words that keep a fixed spelling in display names (keyed by upper-case form).
SPECIAL_CASE = {
    "MLB": "MLB", "NFL": "NFL", "NBA": "NBA", "WNBA": "WNBA", "NHL": "NHL", "MLS": "MLS",
    "UFC": "UFC", "WWE": "WWE", "F1": "F1", "MVP": "MVP", "RC": "RC", "SP": "SP", "SSP": "SSP",
    "USA": "USA", "UK": "UK", "TV": "TV", "II": "II", "III": "III", "IV": "IV", "AL": "AL",
    "NL": "NL", "FDI": "FDI", "1/1": "1/1", "ASCC": "ASCC", "EA": "EA", "SE": "SE", "CEE": "CEE",
    "RAYWAVE": "RayWave", "FROZENFRACTOR": "FrozenFractor", "XFRACTOR": "XFractor",
    "X-FRACTOR": "X-Fractor", "SUPERFRACTOR": "Superfractor", "FOILFRACTOR": "FoilFractor",
    "MINIONFRACTOR": "MinionFractor", "LOGOMAN": "Logoman", "DEGROM": "deGrom",
}
# "X" as in "Topps Chrome x Jennie" / "Topps x Sesame Street" (Topps prints it lower-case).
SMALL_WORDS = {"OF", "AT", "TO", "AND", "THE", "IN", "ON", "A", "AN", "FOR", "BY", "VS", "VS.", "OR", "X"}

ORDINAL_RE = re.compile(r"^(\d+)(ST|ND|RD|TH)$")
YEAR_RE = re.compile(r"^(19|20)\d\d$")

QUOTE_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "–": "-", "—": "-", "−": "-", " ": " ",
}


def clean_space(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def normalize_quotes(s: str) -> str:
    for a, b in QUOTE_MAP.items():
        s = s.replace(a, b)
    return s


def has_lower(s: str) -> bool:
    return any(ch.islower() for ch in s)


def _title_word(word: str, first: bool) -> str:
    up = word.upper()
    if up in SPECIAL_CASE:
        return SPECIAL_CASE[up]
    if not first and up in SMALL_WORDS:
        return word.lower()
    m = ORDINAL_RE.match(up)
    if m:
        return m.group(1) + m.group(2).lower()
    if "-" in word and len(word) > 1:
        parts = word.split("-")
        return "-".join(_title_word(p, first and i == 0) if p else p for i, p in enumerate(parts))
    if "/" in word and len(word) > 1:
        return "/".join(_title_word(p, first) if p else p for p in word.split("/"))
    # leading punctuation such as "(" or quotes (accented letters are letters, not punctuation)
    i = 0
    while i < len(word) and not word[i].isalnum():
        i += 1
    j = len(word)
    while j > i and not word[j - 1].isalnum():
        j -= 1
    lead, core, trail = word[:i], word[i:j], word[j:]
    if lead or trail:
        if not core:
            return word
        return lead + _title_word(core, first) + trail
    if up.isdigit():
        return word
    if "'" in core:
        # O'NEIL -> O'Neil, COMMISSIONER'S -> Commissioner's
        bits = core.split("'")
        out = [bits[0][:1].upper() + bits[0][1:].lower()]
        for b in bits[1:]:
            out.append(b.lower() if len(b) <= 1 else b[:1].upper() + b[1:].lower())
        return "'".join(out)
    return core[:1].upper() + core[1:].lower()


def smart_title(s: str) -> str:
    """Display casing. Text that already has lower-case letters is kept as is."""
    s = clean_space(normalize_quotes(s))
    if not s or has_lower(s):
        return s
    words = s.split(" ")
    return " ".join(_title_word(w, i == 0) for i, w in enumerate(words))


def slugify(s: str) -> str:
    s = normalize_quotes(s or "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("&", " and ").replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "x"


def unique_id(base: str, used: set) -> str:
    ident = base
    n = 2
    while ident in used:
        ident = "%s-%d" % (base, n)
        n += 1
    used.add(ident)
    return ident


def clean_team(s: str) -> str:
    s = re.sub(r"[®™©]", "", s or "")
    return clean_space(s)


def clean_name(s: str) -> str:
    """Player name for display: trademark glyphs (®/™/©) removed, as for teams."""
    return clean_team(s)


def fold_accents(s: str) -> str:
    """'EXPOSÉ' -> 'EXPOSE' (NFKD, combining marks dropped)."""
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(ch for ch in s if not unicodedata.combining(ch))


# ---------------------------------------------------------------- matching tokens

SYNONYMS = {
    "AUTO": "AUTOGRAPH", "AUTOS": "AUTOGRAPH", "AUTOGRAPHED": "AUTOGRAPH",
    "AUTOGRAPHS": "AUTOGRAPH", "RELICS": "RELIC", "CARDS": "CARD", "PLATES": "PLATE",
    "PATCHES": "PATCH", "SWATCHES": "SWATCH",
}
# Tokens that never decide a match on their own ("filler").
SOFT_TOKENS = {
    "TOPPS", "CHROME", "BASEBALL", "FOOTBALL", "BASKETBALL", "SOCCER", "HOCKEY", "CARD",
    "REDEMPTION", "OF", "THE", "AND", "X", "&", "INSERT", "PARALLEL", "SET",
}
# Tokens that are soft only when they appear in a *section* name.
SECTION_SOFT_TOKENS = {"REFRACTOR"}


NO_SINGULAR = {"TOPPS", "SERIES", "ATLAS", "CHAOS", "BONUS", "NEXUS", "PLUS", "GLASS", "CLASS",
               "TEXAS", "LAS", "BOSS", "PRESS", "ACROSS", "THIS", "ALIAS"}


def singular(tok: str) -> str:
    if tok in SYNONYMS:
        return SYNONYMS[tok]
    if tok in NO_SINGULAR:
        return tok
    if len(tok) > 3 and tok.endswith("S") and not tok.endswith("SS") and not tok.endswith("US") \
            and not tok.endswith("IS") and not tok[:-1].isdigit():
        tok = tok[:-1]
    return SYNONYMS.get(tok, tok)


def norm_token(tok: str) -> str:
    t = fold_accents(normalize_quotes(tok)).upper()
    t = t.replace("'", "")
    t = re.sub(r"[^A-Z0-9&\-]", "", t)
    t = t.strip("-")
    if not t:
        return ""
    return singular(t)


def raw_tokens(s: str):
    """Split a raw name into display tokens (whitespace separated)."""
    return [t for t in clean_space(normalize_quotes(s)).split(" ") if t]


def is_year(tok: str) -> bool:
    return bool(YEAR_RE.match(tok))


# Words that mark a section as an autograph / relic (memorabilia) card. `strict` = only the
# literal AUTOGRAPH / RELIC words.
STRICT_AUTO = {"AUTOGRAPH"}
STRICT_RELIC = {"RELIC"}
TYPE_AUTO = {"AUTOGRAPH", "SIGNATURE"}
TYPE_RELIC = {"RELIC", "PATCH", "MEMORABILIA", "JERSEY", "MATERIAL", "SWATCH"}


def name_type_words(s: str, strict: bool = False):
    """Return (has_autograph, has_relic) for a section/odds name.

    "(NON-AUTOGRAPH)" style tokens do not count."""
    autos = STRICT_AUTO if strict else TYPE_AUTO
    relics = STRICT_RELIC if strict else TYPE_RELIC
    has_auto = has_relic = False
    for tok in re.split(r"[\s/]+", fold_accents(normalize_quotes(s)).upper()):
        tok = tok.strip("()[],.")
        if not tok or tok.startswith("NON-") or tok.startswith("NON "):
            continue
        for part in tok.split("-"):
            p = singular(re.sub(r"[^A-Z0-9]", "", part))
            if p in autos:
                has_auto = True
            if p in relics:
                has_relic = True
    return has_auto, has_relic
