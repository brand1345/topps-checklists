# Topps Checklists — Architecture Spec (v1)

This document is the **contract** between the PDF pipeline (`pipeline/`) and the static site (`site/`).
Both sides must follow it exactly. If you need to change the schema, change this file first.

## Goals

1. Turn the two official Topps PDFs for a set (a **checklist PDF** and an **odds PDF**) into one JSON file.
2. Render that JSON as a sleek, fast, static site split into: **Base & Parallels**, **Inserts**,
   **Case Hits** (hard-to-pull inserts), **Autographs**, **Relics**.
3. Be **rebuildable for every future set** with zero code changes: drop two PDFs in a folder, run one
   command. Anything the heuristics get wrong is fixed in a per-set `set.yaml`, never by editing JSON.
4. Hovering a parallel's name shows an example card image (real image if provided, otherwise a
   generated "swatch" card mock in that parallel's color/pattern).

## Repository layout

```
sets/<slug>/checklist.pdf      # official Topps checklist (input)
sets/<slug>/odds.pdf           # official Topps odds sheet (input)
sets/<slug>/set.yaml           # per-set config + overrides (hand-editable, commented)
sets/<slug>/images/            # optional example images (see "Images")
pipeline/                      # Python 3.9+ package: `python -m pipeline ...`
  __main__.py                  # CLI
  checklist.py                 # checklist PDF -> sections/cards
  odds.py                      # odds PDF -> formats/rows
  match.py                     # odds rows -> (section, parallel)
  classify.py                  # category + rarity tier
  names.py                     # display-name casing, slugify, normalization helpers
  build.py                     # orchestrates, writes site/data + reports
tests/                         # unittest-based tests (`python -m unittest`)
site/                          # static site, NO build step (vanilla ES modules + CSS)
  index.html
  assets/                      # app.js, *.js modules, styles.css
  data/sets.json               # GENERATED index of all sets
  data/<slug>.json             # GENERATED per-set data
  data/<slug>/images/*         # GENERATED copy of sets/<slug>/images
reports/<slug>.md              # GENERATED human-readable parse/match report
fixtures/                      # local-only (gitignored) PDFs from other Topps sets for robustness tests
.github/workflows/deploy.yml   # CI: build pipeline -> deploy site/ to GitHub Pages
```

Python deps: `pdfplumber`, `pyyaml` only (see `requirements.txt`). Local venv at `.venv/`
(`.venv/bin/python`). Must run on Python 3.9 (local) and 3.11+ (CI) — no `match` statements,
no `X | Y` type unions at runtime.

## CLI

```
python -m pipeline build [<slug> ...] [--sets-dir sets] [--out-dir site/data] [--reports-dir reports]
                                             # build all (or listed) sets -> site/data + reports
python -m pipeline new <slug> --checklist PATH [--odds PATH] [--name "2027 Topps Chrome Baseball"] [--sets-dir sets]
                                             # scaffold sets/<slug>/ with PDFs + starter set.yaml
python -m pipeline inspect <pdf> [--kind {auto,checklist,odds}] [--lines] [--cards]
                                             # debug dump of what the parser sees (headers, rows, columns)
```

Pruning (below) compares `--out-dir` against `--sets-dir`, so pass both together: building another
sets folder (e.g. `--sets-dir fixtures`) into the default `site/data` would prune the real sets.
Make wrappers: `make build [SLUG=…]`, `make new SLUG=… CHECKLIST=… [ODDS=…] [NAME=…]`,
`make inspect PDF=… [ARGS=…]`, `make check` (tests, then build).

`build` must:
- never crash on an unexpected row: record a warning and continue;
- fail a set (print `[<slug>] FAILED: <reason>`, exit non-zero at the end) only if one of its PDFs
  can't be opened/parsed at all (including a checklist with no extractable text, e.g. a scan), its
  `set.yaml` is not valid YAML (the message names the line), or a set named on the command line
  has no checklist PDF. A failing set never stops the other sets or the `sets.json` index;
- print a short summary per set (sections, cards, odds rows, matched/unmatched counts, warnings);
- when building all sets, delete the generated output (`site/data/<slug>.json`,
  `site/data/<slug>/`, `reports/<slug>.md`) of sets whose `sets/<slug>/` folder no longer exists,
  and warn when two sets share a `name`.

`new` validates the slug (`^[a-z0-9]+(-[a-z0-9]+)*$`), parses both PDFs before creating
`sets/<slug>/` (a failed `new` leaves nothing behind), and `--odds` is optional (a set without an
odds PDF builds with a warning; add `odds.pdf` later and fill in `formats:`).
PDF discovery in `sets/<slug>/`: `checklist.pdf` / `odds.pdf`, else any PDF whose name contains
"checklist" / "odds" (case-insensitive), else (two PDFs at most) by content (an odds sheet is dense
with `1:x` values).

## PDF formats (observed)

### Checklist PDF
- Spreadsheet printed to PDF; Verdana. **Bold** lines are headers, regular lines are card rows.
  If a checklist has no bold lines at all, headers are guessed from a larger type size or short
  all-caps single-cell lines, with a warning.
- Page furniture is dropped: spreadsheet column-header rows (`Card # | Player | Team | Rookie`),
  footers (`Page 1 of 2`) and title lines repeated at the same position on most pages. A
  group/section header repeated at the top of a page, or `<SECTION> (CONTINUED)`, continues the
  open section. A section header directly followed by another header inside a known group
  (`BASE`, `INSERT`, `AUTOGRAPH`, …) is an empty section ("No cards listed in the checklist"),
  not a new group.
- Header hierarchy: a **group** header (`BASE`, `INSERT`, `AUTOGRAPH`, `RELIC`, `AUTOGRAPH RELIC`, …)
  followed by **section** headers (`BASE CARDS`, `ULTRAVIOLET`, `ROOKIE AUTOGRAPHS`, …).
  A group header may be followed directly by cards (then the group is also the section).
- Card row columns (by x position): **code** (e.g. `1`, `UV-1`, `RA-AA`, `91CB-1`; may be empty),
  **player name**, **team** (with ®/™), optional **Rookie** flag column.
  Columns are vertical gutters that (almost) no row crosses (~2% of rows may cross, at least one
  once there are 20 rows). Cell text is built from words in content-stream order and each word
  goes whole to the column where it starts, so a long name that runs into the team column is
  never split mid-word.
- The flag column may hold values other than Rookie/RC (`Future Stars`, `Combo Card`, a country on
  a dual card's code line): those become the card's `tags`, never part of the team.
- The Rookie column may be on the same page OR overflow onto trailing pages (2026 Chrome: pages
  33–63 hold only "Rookie" words for pages 1–31, aligned by y-position; an all-blank trailing
  overflow page may be omitted). Rookie flags must be mapped back to rows by (page, y).
  An overflow page has no headers and all its text in one narrow column. Interleaved layouts
  (main, overflow, main, overflow, …) map each overflow page to the main page before it; trailing
  layouts map overflow pages to main pages in order by best y-alignment of flags to rows, page
  order only breaking ties (so a blank overflow page that was left out does not shift later pages;
  a mapping that differs from page order is reported).
- The first lines of page 1 may be a title (e.g. "2026 Topps Chrome Baseball Checklist") and a
  disclaimer in italics — not headers.
- Multi-player cards: consecutive rows in the same section with the **same code** are ONE card with
  multiple players (e.g. `PTP-1` Mantle + Judge, `DA-SD` Sosa + Dawson) — unless the row repeats a
  player already on that card (then it is a second card, with a warning). A code printed once,
  centred between two code-less rows, is a two-player card when the section's cards look like that;
  in a section of one-row cards it is one player whose name wrapped onto two lines. Code-less rows
  join the coded row above only when at least two rows are coded and no card would exceed 6 rows;
  cards with more than 4 players are reported.
- Rows may lack a code (e.g. "FANATICS AUTHENTICS REDEMPTION CARDS"), or lack a player name
  (e.g. `CT-1 Los Angeles Dodgers®` — a team card).
- Some PDFs have no space between code and name in extracted text (`1Marvin Harrison Jr.`) —
  always use word x-positions, not text splitting.

### Odds PDF
- Landscape table, ArialMT. Title/disclaimer lines, then a header row: first column label
  (`Card`, `Cards`, `All Components`, `COMPONENT`, …) and one column per **format**
  (e.g. `6625 - MLB-CHROME 2026` / `HOBBY`, … `BREAKER` / `DELIGHT`, `FANATICS`). Header can span
  two lines. Header repeats on every page.
- Each row: a name (e.g. `BASE CARDS GOLD REFRACTOR`) + one value per format, right-aligned.
- Values: `1:341`, `1:1,705`, `-` (not available in that format). Source errors exist and must
  be preserved, not invented: `1:1,2175` (bad separator), `0.39374999999999999` (Excel artifact).
- Values may also be plain thousands without commas (`1:6818`: well-formed) or `N/A` (= `-`).
- Column positions come from the numeric values; `-` cells never create a column unless a format
  label sits above them (a format with no odds at all).
- Long names wrap onto a following line that has no values (e.g. `... GREEN GEOMETRIC` + `REFRACTOR`).
  Append continuation lines to the previous row's name — only lines within 1.5 row pitches below
  it that start in the name column. A value-less line just above a row whose values have no name
  (values vertically centred on a wrapped name) starts that row's name. Other value-less lines
  (footers, notes) are ignored with a warning. A disclaimer that never ends in `vary.` / `.` /
  `**` stops at the first odds row (or after 6 lines), with a warning.
- The format label drops the product code and everything up to the last year token
  (`6625 - NBA CHROME 2025-26 HOBBY` → `HOBBY`).

## Matching odds rows → checklist sections

Odds names = `<section name variant> <parallel name>`; names don't match exactly. Examples (2026 Chrome):

| Odds row | Section | Parallel |
|---|---|---|
| `BASE CARDS REFRACTOR` | BASE CARDS | Refractor |
| `BASE CARDS TOPPS 75TH ANNIVERSARY` | BASE CARDS | Topps 75th Anniversary |
| `BASE CARDS IMAGE VARIATIONS GOLD REFRACTOR` | BASE CARDS IMAGE VARIATIONS | Gold Refractor |
| `BASE CARDS SUPER SHORT PRINTS` | SUPER SHORT PRINTS | (base version) |
| `CHROME RADIATING ROOKIES` | TOPPS CHROME RADIATING ROOKIES | (base) |
| `MVP BUYBACKS PRISM` | 2025 CHROME MVP BUYBACKS | Prism |
| `TOPPS CHROME CHAMPION GOLD` | TOPPS CHROME CHAMPION REFRACTORS | Gold |
| `TOPPS CHROME ROOKIE AUTOGRAPHS TEAL REFRACTOR` | ROOKIE AUTOGRAPHS | Teal Refractor |
| `TOPPS CHROME RETAIL ROOKIE AUTOGRAPHS GOLD RAYWAVE REFRACTOR` | RETAIL ROOKIE AUTOGRAPHS | Gold RayWave Refractor |
| `TOPPS CHROME LEGENDS AUTOGRAPHS RED REFRACTOR` | CHROME LEGEND AUTOGRAPHS | Red Refractor |
| `1991 TOPPS CHROME AUTOGRAPHS ORANGE` | 1991 TOPPS BASEBALL AUTOGRAPHS | Orange |
| `2025 WORLD SERIES CHAMPIONS AUTOGRAPHS GOLD REFRACTOR` | 2025 WORLD CHAMPIONS AUTOGRAPH REFRACTOR | Gold Refractor |
| `WORLD SERIES CHAMPIONS AUTOGRAPHS SUPERFRACTOR` | WORLD SERIES CHAMPIONS AUTOGRAPHS | Superfractor |
| `CLASS OF 2026 COOPERSTOWN CALLS AUTOGRAPH VARIATION BLACK` | COOPERSTOWN CALLS AUTOGRAPH VARIATION | Black |
| `TOPPS CHROME MVP BUYBACKS AUTOGRAPHS` | 2025 CHROME MVP BUYBACKS AUTOGRAPHS | (base) |
| `2025 MLB COMMISSIONER’S TROPHY` | 2025 MLB COMMISSIONERS TROPHY | (base) |
| `GOLD LOGOMAN RELICS REDEMPTION CARD` | GOLD LOGOMAN RELICS | (base; redemption) |
| `75TH DIAMOND AUTOGRAPHS PRINTING PLATES` | 75TH DIAMOND AUTOGRAPHS | Printing Plates |

Required behaviour:
- Heuristic matcher (normalize case/punctuation/apostrophes/accents, singularize plurals, treat
  filler tokens like TOPPS / CHROME / sport words / REFRACTORS-in-section-names / CARD(S) /
  REDEMPTION as soft, years must agree when both sides have one, type words AUTOGRAPH/RELIC in the
  odds name constrain the section to the matching group, prefer the section explaining the most
  odds tokens; the leftover suffix is the parallel name; empty suffix = the section's base version).
  A year in the section name that the odds name lacks is a strong penalty (`BASE CARDS GOLD` is not
  `1991 TOPPS FOOTBALL CHROME BASE CARDS`); series markers (I, II, III, IV, SERIES) missing from the
  odds name barely count; an odds name without any autograph/relic word is strongly penalised for
  an AUTOGRAPH/RELIC section token it lacks; split and joined spellings match (`ULTRA VIOLET` =
  `ULTRAVIOLET`).
- `set.yaml` `aliases` override the heuristic (exact odds-row prefix → section raw name). An alias
  that matches no odds row, or whose target section doesn't exist, is reported as a warning.
- Two odds rows that would give a section the same parallel name are told apart by the words of
  their section part that differ (`... AUTOGRAPHS DRUSKI REFRACTORS ORANGE` / `... SPIKE LEE ...` →
  `Druski Refractors Orange`, `Spike Lee Refractors Orange`).
- Every odds row ends up either matched (section + parallel) or in `unmatchedOdds` — never dropped.
- The report `reports/<slug>.md` lists every odds row → section / parallel (+ how it was matched:
  `exact`, `heuristic`, `alias`), unmatched rows, sections without any odds, and all warnings.
- A trailing `REDEMPTION CARD(S)` in an odds name marks the section `redemption: true`; it is not a parallel.

## Classification

Each section gets `kind`, `category`, and `tier`.

- `kind`: `base` | `variation` | `insert` | `autograph` | `relic` | `autograph-relic`
  - group BASE → `base`; group AUTOGRAPH → `autograph`; group RELIC → `relic`;
    group AUTOGRAPH RELIC (or a RELIC section whose name contains AUTOGRAPH) → `autograph-relic`.
  - group INSERT → `variation` if the name contains VARIATION, SUPER SHORT PRINT, or starts with
    BASE CARDS; otherwise `insert`.
  - other/unknown groups (or everything under BASE): the name decides — autograph words
    AUTOGRAPH/SIGNATURE(S), relic words RELIC/PATCH/MEMORABILIA/JERSEY/MATERIAL/SWATCH (not after
    NON-), INSERT, SHORT PRINT/SSP/VARIATION.
  - an `insert` whose every card has a plain-number code and is the same number and player(s) as a
    `base` card is a `variation` (an image-variation set such as MINIONS MLB).
- `tier` (rarity of the section's base version, else its most common parallel) from the **primary
  format** (first odds column unless `set.yaml` says otherwise). With `n` = packs per hit,
  `P` = packsPerBox, `C` = packsPerBox × boxesPerCase:
  - `common`: n ≤ P (≥ 1 per box) · `short-print`: n ≤ C (≥ 1 per case) ·
    `case-hit`: n ≤ 10·C · `ultra`: n > 10·C. No odds anywhere → `null`.
  - If the section is absent from the primary format, use the format where it's most common
    (using that format's packs config if known, else the primary's) and set `tierBasis.format`.
  - Thresholds are configurable in `set.yaml` (`tiers:`). Defaults: P = 20, boxesPerCase = 12.
- `category` (site tab): `base`/`variation` → `base`; `insert` with tier `case-hit` or `ultra` →
  `case-hits`, other inserts → `inserts`; `autograph` → `autographs`; `relic`/`autograph-relic` → `relics`.
  An insert with no odds (tier `null`) takes the category of an insert with odds whose name is the
  same apart from 4-digit years (CLASS OF 2026 / CLASS OF 2025 COOPERSTOWN CALLS), with a note.
- `tierBasis.perBox` / `perCase` are rounded to 4 decimals, keeping 4 significant figures for tiny
  rates (`7.02e-06`, never `0.0`). When the basis value carries a source `error`, the section gets a
  note saying so.
- `set.yaml` `overrides.sections.<sectionId>` can force `category`, `tier`, `kind`, `name`, `hidden`.

## Output JSON — `site/data/<slug>.json`

```jsonc
{
  "schemaVersion": 1,
  "slug": "2026-topps-chrome-baseball",
  "name": "2026 Topps Chrome Baseball",
  "year": 2026, "sport": "Baseball", "brand": "Topps",
  "generatedAt": "2026-10-03T22:00:00Z",       // ISO UTC
  "disclaimer": "Checklists and odds provided by Topps reflect …",  // from the PDFs
  "formats": [                                   // odds columns, in PDF order
    { "id": "hobby", "label": "Hobby", "raw": "6625 - MLB-CHROME 2026 HOBBY", "code": "6625",
      "packsPerBox": 20, "boxesPerCase": 12, "primary": true }
    // packsPerBox / boxesPerCase may be null when unknown
  ],
  "categories": [                                // fixed order, always all five
    { "id": "base", "label": "Base & Parallels", "sectionCount": 6 },
    { "id": "inserts", "label": "Inserts", "sectionCount": 0 },
    { "id": "case-hits", "label": "Case Hits", "sectionCount": 0 },
    { "id": "autographs", "label": "Autographs", "sectionCount": 0 },
    { "id": "relics", "label": "Relics", "sectionCount": 0 }
  ],
  "sections": [                                  // checklist order
    {
      "id": "base-cards",                        // slug of rawName, unique within set (suffix -2 on clash)
      "name": "Base Cards",                      // display name (smart title case)
      "rawName": "BASE CARDS",
      "group": "BASE",                           // raw group header
      "kind": "base",
      "category": "base",
      "tier": "common",                          // or null
      "tierBasis": { "format": "hobby", "n": 1, "perBox": 20.0, "perCase": 240.0 },  // or null
      "redemption": false,
      "cardCount": 300,
      "rookieCount": 87,
      "cards": [
        { "code": "1", "rookie": false,
          "players": [ { "name": "Shohei Ohtani", "team": "Los Angeles Dodgers", "rookie": false } ] }
        // team and name strings have ®/™/© stripped; name may be "" for team cards; code may be ""
        // optional "tags": ["Future Stars"] — other flag-column text of the card (present only when
        // non-empty), e.g. a dual card's country
      ],
      "odds": { "hobby": { "raw": "1:3", "n": 3 }, "jumbo": null },   // base version; null value = not in that format;
                                                 // the whole field is null if no base-version row exists
      "oddsName": "BASE CARDS",                  // raw odds row name used for `odds`, or null
      "parallels": [                             // odds order (as in PDF)
        {
          "id": "gold-refractor",                // slug, unique within section
          "name": "Gold Refractor",              // display name (known parallel words get their canonical
                                                 // spelling: "SuperFractor" -> "Superfractor")
          "rawName": "BASE CARDS GOLD REFRACTOR",// full raw odds row name, exactly as printed (curly quotes kept)
          "odds": { "hobby": { "raw": "1:341", "n": 341 }, "fanatics": { "raw": "1:8,020", "n": 8020 } },
          "formats": ["hobby", "jumbo", "value", "mega", "breaker-delight", "fanatics"],  // where available
          "image": null,                         // relative URL e.g. "data/<slug>/images/gold-refractor.jpg"
          "match": "heuristic"                   // exact | heuristic | alias
        }
      ],
      "image": null,                             // example image for the base version
      "notes": []                                // e.g. ["No odds listed for this section",
                                                 //  "Listed by Topps without odds in any format: Sapphire, …"]
    }
  ],
  "unmatchedOdds": [ { "rawName": "…", "odds": { /* same shape */ } } ],
  "warnings": [ "…" ],
  "stats": { "sections": 70, "cards": 1400, "rookies": 300, "parallels": 280, "oddsRows": 330 }
}
```

Odds value objects: `{ "raw": "<exact source text>", "n": <int packs-per-hit> }`. If the raw value
can't be parsed confidently, `n` is `null` and an `"error": "<short reason>"` is added (e.g. raw
`1:1,2175` → `n: 12175`, `"error": "malformed number in source"`; raw `0.39374999999999999` →
`n: null`, `"error": "unreadable value in source"`). Format ids are slugs of the format label.

`site/data/sets.json`:
```json
{ "schemaVersion": 1,
  "sets": [ { "slug": "…", "name": "…", "year": 2026, "sport": "Baseball",
              "cards": 1400, "sections": 70, "generatedAt": "…" } ] }
```
Sorted newest year first, then name, then slug. Only sets that still have a `sets/<slug>/` folder
are listed.

## set.yaml (per set, hand-editable, every key optional except `name`)

```yaml
name: 2026 Topps Chrome Baseball
year: 2026
sport: Baseball
primaryFormat: hobby
formats:                       # keyed by detected format id; label/packs are editable
  hobby:            { label: Hobby, packsPerBox: 20, boxesPerCase: 12 }
  breaker-delight:  { label: "Breaker's Delight" }
tiers:                         # optional threshold overrides (in packs)
  # commonMax: 20
  # shortPrintMax: 240
  # caseHitMax: 2400
aliases:                       # odds-row prefix -> checklist section rawName
  # "TOPPS CHROME LEGENDS AUTOGRAPHS": "CHROME LEGEND AUTOGRAPHS"
overrides:
  sections:
    # helix: { category: case-hits }
images:                        # optional explicit image URLs (relative to sets/<slug>/images or absolute https)
  # "base-cards/gold-refractor": gold.jpg
  # "*/superfractor": https://example.com/superfractor.jpg
```

`python -m pipeline new` writes a starter `set.yaml` with detected name/year/sport and every detected
format listed (packs `null` except as known), with explanatory comments. Empty sections are written
as a bare `key:` line followed by commented examples, so deleting the `#` of an example line gives
valid YAML. Year/sport fall back to a two-digit year in the slug (`…-26cubk` → 2026) and league
names in section names (NBA, NFL, MLB, MLS, WNBA, NHL).

The build validates `set.yaml`: invalid YAML fails the set with the line number; a key written twice
in one mapping is an error (PyYAML would silently keep the last one); unknown keys (with a "did you
mean" suggestion), values of the wrong type and non-numeric packs are warnings and are ignored.
Known keys: top level as above; `formats.<id>`: label, packsPerBox, boxesPerCase; `tiers`:
commonMax, shortPrintMax, caseHitMax; `overrides.sections.<id>`: category, tier, kind, name, hidden.

## Images

Resolution order for a parallel `P` in section `S` (first hit wins), files in `sets/<slug>/images/`
with extension jpg/jpeg/png/webp/avif/gif:
1. `images:` key `"<S.id>/<P.id>"` in set.yaml; 2. file `<S.id>--<P.id>.*`;
3. `images:` key `"*/<P.id>"`; 4. file `<P.id>.*` (generic example for that parallel across sections).
Base version of a section: key `"<S.id>"` / file `<S.id>.*`.
If nothing matches `P.id`, the same steps are tried with its singular form (`superfractors` →
`superfractor`). URLs must be `https://` (an `http://` URL is ignored with a warning).
Matched files are copied to `site/data/<slug>/images/` (emptied first, so removed images disappear)
and referenced relatively. No image → `null` and the site renders a generated swatch card.
`images:` keys and image files that match nothing, and files named in set.yaml that don't exist, are reported
once each; the report has an "Images" section listing every image used.

## Site (static, vanilla JS)

- `site/index.html` + ES modules in `site/assets/`. No bundler, no npm dependencies, no frameworks.
  Google Fonts allowed. Must work from `python -m http.server -d site`.
- Data root defaults to `data/`; dev override via `?data=<path>` query param.
- Hash routes: `#/<slug>` (overview), `#/<slug>/<category>`, `#/<slug>/<category>/<sectionId>`,
  `#/<slug>/search/<query>`. Unknown/missing slug → newest set.
- Header: set switcher, global search (player / team / card code / section), format picker
  (Hobby, Jumbo, … from `formats`) that controls which odds are shown everywhere (remembered in
  localStorage, wrapped in try/catch).
- Tabs: Overview · Base & Parallels · Inserts · Case Hits · Autographs · Relics (with counts).
- Section cards: name, card count, RC count, tier badge, base odds for selected format
  (+ "≈ 1 per N boxes / cases" when packs config known), parallel "rainbow" chips sorted by rarity.
  Expanding a section shows the full card list (code, players, team, RC badge), filterable.
- Hover/focus (tap on touch) a parallel chip or name → floating preview: image if `image` set,
  else a generated CSS card mock styled for that parallel (gold, orange, black, red, blue, green,
  purple, pink, aqua, teal, yellow, white, refractor sheen, prism, wave, raywave, geometric,
  x-fractor, negative, superfractor, frozenfractor, printing plate, sapphire, padparadscha,
  tie-dye, …) plus odds across all formats.
- Overview: set stats, tier legend, rarest pulls in the selected format, rookies list.
- Light + dark theme (prefers-color-scheme + toggle), responsive down to 360px, keyboard
  accessible, no horizontal page scroll on mobile.
- Tier display labels: `common` → Common, `short-print` → **Uncommon** (the id is unchanged),
  `case-hit` → Case Hit, `ultra` → Ultra. When the selected format differs from the tier's basis
  format (`tierBasis.format`, else the primary format), the badge adds "· <basis format>".
- Player rookie status (RC badge on a player, overview Rookies list): if the player has a card in a
  `kind: "base"` section, they are a rookie only when that base card's player entry has `rookie: true`;
  otherwise any RC-flagged card counts. Per-card RC badges still follow each card's own flag.
- Search understands filter words besides free text: `rc`/`rookie(s)` (RC-flagged cards only), a
  format label or id (`mega`, `value box`, `breakers delight`, … → sections/parallels with odds in that
  format; odds shown in it), and tier words (`case hit`, `ultra`, `uncommon`). An exact card-code
  match ranks first. Following a result's section header opens that section with its filter prefilled.
- Back/forward restores the previous scroll position (per history entry, sessionStorage-backed).
  Unknown section ids / category segments in the hash are rewritten to the canonical route.
