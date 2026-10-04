# Adding a new set

This guide takes a new Topps release from its two PDFs to the live site
(<https://brand1345.github.io/topps-checklists/>). You don't need to write any code. You run a
few commands in Terminal and sometimes edit a settings file (`set.yaml`). Plan on about 15 minutes.

All commands are run from the repo folder (`cd topps-checklists`). The examples use
`2027-topps-chrome-baseball`, so swap in your own set.

---

## 0. One-time setup

You need Python 3.9 or newer (`python3 --version`), `git` and `make`. On a Mac, run
`xcode-select --install` once if `make` or `git` is missing. Then get the repo and set it up:

```sh
git clone https://github.com/brand1345/topps-checklists.git
cd topps-checklists
make setup
```

`make setup` creates a private Python environment in `.venv/`. Run it again if you ever see
`Python not found at '.venv/bin/python'`.

## 1. Download the two PDFs

Topps publishes two PDFs for every release, linked from the product's page on topps.com:

| PDF | What it looks like |
|---|---|
| **Checklist** | A long list of every card: code (`1`, `UV-1`, `RA-AA`), player, team and a "Rookie" column, under bold headers such as `BASE`, `INSERT`, `AUTOGRAPH` and `RELIC`. |
| **Odds** | A wide table with rows like `BASE CARDS GOLD REFRACTOR` and one column per box type (`HOBBY`, `JUMBO`, `MEGA`, `BREAKER DELIGHT`, …), with values like `1:341`. |

Use the **final** checklist. Topps sometimes posts an early version first; the 2026 Chrome file,
for example, was named `…_Checklist_Final_7.22.pdf`.

## 2. Create the set

Pick a **slug**: the set's ID in lowercase with hyphens, in the form year-brand-product-sport, e.g.
`2027-topps-chrome-baseball`. It becomes the folder name and the site address (`#/2027-topps-chrome-baseball`).

```sh
make new SLUG=2027-topps-chrome-baseball \
         CHECKLIST=~/Downloads/2027_Topps_Chrome_Baseball_Checklist.pdf \
         ODDS=~/Downloads/2027_Topps_Chrome_Baseball_Odds.pdf \
         NAME="2027 Topps Chrome Baseball"
```

- `NAME` is optional. If you leave it out, the name is detected from the PDF. Check it in `set.yaml` afterwards.
- **The easiest way to enter a path is to drag the file in.** Type `CHECKLIST=` (no space after
  the `=`), then drag the file from Finder into the Terminal window. Terminal pastes the full path
  and puts a backslash in front of every space and bracket, e.g.
  `…/2027_Topps_Chrome_Baseball_Odds\ \(1\).pdf`. Leave it exactly like that, **without quotes**.
- **If you type a path yourself** and it has spaces or brackets, put the whole path in double quotes:
  `ODDS="~/Downloads/2027_Topps_Chrome_Baseball_Odds (1).pdf"`.
- Don't combine the two. Quotes around a dragged path keep the backslashes as part of the name.
  `make new` notices this and removes them, but other commands (such as `make inspect`) don't.

This runs `python -m pipeline new <slug> --checklist … --odds … [--name …]` and creates:

```
sets/2027-topps-chrome-baseball/
  checklist.pdf    the checklist PDF
  odds.pdf         the odds PDF
  set.yaml         settings for this set, pre-filled and commented
```

(You can also set up the folder by hand. Put in the two PDFs named exactly `checklist.pdf` and
`odds.pdf`, plus a `set.yaml` containing at least `name: 2027 Topps Chrome Baseball`.)

Open `set.yaml` in any plain-text editor (VS Code, or TextEdit with *Format → Make Plain Text*).
Check that `name`, `year` and `sport` are right. The rest is covered in steps 5–7.

> **set.yaml tips:** indent with spaces, never tabs. A `#` starts a comment. Put a value in
> double quotes if it contains `:`, `'` or `#`, e.g. `label: "Breaker's Delight"`.

## 3. Build

```sh
make build                                  # every set
make build SLUG=2027-topps-chrome-baseball  # just this one
```

The build prints one summary line per set, like this:

```
[2027-topps-chrome-baseball] 55 sections, 1604 cards (412 RC), 302 parallels, odds rows 349: 349 matched / 0 unmatched, 2 warnings
```

It writes two files:

- `site/data/2027-topps-chrome-baseball.json`, the data the site shows (generated, so **never edit it by hand**);
- `reports/2027-topps-chrome-baseball.md`, the report you read next.

A set only fails to build when a PDF can't be opened at all or `set.yaml` can't be read. You then
see a `[<slug>] FAILED: …` line that says why, instead of the summary line, and the other sets
still build. Anything else the pipeline doesn't understand becomes a warning in the report, and the
rest of the set still builds.

## 4. Read the report

Open `reports/2027-topps-chrome-baseball.md`. VS Code shows it nicely with *Open Preview*
(`Cmd+Shift+V`). From top to bottom it has:

- **A summary**: pages, card rows, rookie flags, odds rows, unmatched rows and warnings.
- **Formats**: the box types (odds columns) found in the odds PDF, with the box configuration from
  step 6.
- **Sections**: one row per checklist section, in checklist order.
  - `id` is the **section ID**. You need it for overrides (step 5B) and image names (step 7).
  - `section` is the name as the checklist prints it. The report always uses these raw names, so a
    `name` override (step 5B) doesn't show here. It shows on the site and in `make ids`.
  - `category` is the tab the section appears in, and `tier` is its rarity (step 5C). Both already
    include your overrides. A hidden section is marked `(hidden)` after its ID.
  - `tier basis` is the format and odds the tier was worked out from.
  - `base odds` are the odds of the section's base version in the primary format. A blank cell
    means the odds sheet has no row for the base version (only for its parallels, or nothing at
    all). A `-` means there is a base-version row, but the primary format doesn't offer it; the
    tier then comes from another format, shown in `tier basis`.
- **Odds rows → sections**: every odds row, the section and parallel it was matched to, and how:
  - `exact`: the names line up exactly;
  - `heuristic (2.05)`: the pipeline's best guess, with a confidence score;
  - `alias`: matched by a rule you wrote in `set.yaml` (step 5A).
- **Unmatched odds rows**: rows that couldn't be attached to any checklist section, with the reason.
  Nothing is dropped, but these won't appear under a section until you fix them.
- **Sections without odds**.
- **Images** (step 7): each example image that was found and what it's used for. A file in
  `images/` that matched nothing is listed as **unused**, which usually means a typo in its name.
- **Warnings**: anything odd the parser noticed.

The heuristic **score** is roughly the number of words of the section name found in the odds row,
minus a penalty for each word that doesn't fit. A row whose best score is 0 or less is left
unmatched. A score of 2 or more with a sensible parallel name is almost always right. Below 2 the
match rests on only one or two words, so check those rows yourself. In 2026 Chrome the lowest scores
were `TOPPS CHROME CHAMPION GOLD` → `TOPPS CHROME CHAMPION REFRACTORS` and `MVP BUYBACKS PRISM`
→ `2025 CHROME MVP BUYBACKS`, and both were right.

What to check, in order:

1. **Unmatched odds rows.** Aim for zero. Fix them with an alias (5A).
2. **Sections without odds.** If one of these looks like an unmatched odds row (or one that went to
   the wrong section), it needs an alias. Some sections really have no odds listed, and that's fine.
3. **Heuristic matches**, lowest scores first. Make sure each row went to the right section and that
   the parallel name reads sensibly (`Gold Refractor`, not `Autographs Gold Refractor`).
4. **Tabs.** Open the site (step 8) and check each section sits in the right tab, especially Case Hits.

Some odds values in Topps' PDFs are wrong at the source, e.g. `1:1,2175` or `0.39374999999999999`.
The pipeline keeps these exactly as printed and flags them rather than guessing. That's expected
and you don't need to fix it.

## 5. Fix problems in set.yaml

Every fix goes in `sets/<slug>/set.yaml`. Then run `make build` again and re-read the report.
Fixes stay in place when you rebuild, and when you replace a PDF with an updated version.

You may not need any. 2026 Chrome needed no aliases or overrides for its odds: the pipeline matched
all 349 odds rows on its own. The examples below use real 2026 Chrome names to show the syntax.

### 5A. An odds row is unmatched or went to the wrong section: add an **alias**

Odds rows name a section a bit differently from the checklist. In 2026 Chrome, the odds sheet says
`TOPPS CHROME LEGENDS AUTOGRAPHS …` while the checklist section is `CHROME LEGEND AUTOGRAPHS`.
The pipeline works that one out by itself, but if it hadn't, this alias would link the two:

```yaml
aliases:
  "TOPPS CHROME LEGENDS AUTOGRAPHS": "CHROME LEGEND AUTOGRAPHS"
```

- **Left side:** the start of the odds row name, copied from the report's `odds row` column.
- **Right side:** the section name as the checklist prints it, copied from the report's `section`
  column.
- Capitals don't matter, and neither do straight versus curly apostrophes (`'` and `’`) or accents.
  Every word must match, though, so copy the names from the report rather than retyping them.
- **The rest of the odds row becomes the parallel name.** That one alias handles every row that starts with it:

  | Odds row | Section | Parallel |
  |---|---|---|
  | `TOPPS CHROME LEGENDS AUTOGRAPHS GOLD REFRACTOR` | CHROME LEGEND AUTOGRAPHS | Gold Refractor |
  | `TOPPS CHROME LEGENDS AUTOGRAPHS RED REFRACTOR` | CHROME LEGEND AUTOGRAPHS | Red Refractor |
  | `TOPPS CHROME LEGENDS AUTOGRAPHS SUPERFRACTOR` | CHROME LEGEND AUTOGRAPHS | Superfractor |

  If nothing is left after the alias, the row is the section's **base version** (its main odds).

More examples of the format, again using 2026 Chrome names:

```yaml
aliases:
  "TOPPS CHROME LEGENDS AUTOGRAPHS": "CHROME LEGEND AUTOGRAPHS"
  "1991 TOPPS CHROME AUTOGRAPHS": "1991 TOPPS BASEBALL AUTOGRAPHS"          # ... ORANGE -> Orange
  "2025 WORLD SERIES CHAMPIONS AUTOGRAPHS": "2025 WORLD CHAMPIONS AUTOGRAPH REFRACTOR"
  "MVP BUYBACKS": "2025 CHROME MVP BUYBACKS"                               # ... PRISM -> Prism
```

Aliases take priority over the pipeline's own guess, so they also fix a row that went to the
**wrong** section. Keep each alias specific enough that it only catches the rows you mean.
`"2025 WORLD SERIES CHAMPIONS AUTOGRAPHS"` doesn't touch `WORLD SERIES CHAMPIONS AUTOGRAPHS …`,
because that row doesn't start with `2025`.

If the right-hand name doesn't match any section, the rows the alias catches are listed under
**Unmatched odds rows** with the reason `alias target … not found`.

A trailing `REDEMPTION CARD` / `REDEMPTION CARDS` on an odds row isn't treated as a parallel. It
marks the section as a redemption. For example, `GOLD LOGOMAN RELICS REDEMPTION CARD` is the base
version of `GOLD LOGOMAN RELICS`.

### 5B. A section is in the wrong tab, has the wrong rarity or name, or should be hidden: add an **override**

```yaml
overrides:
  sections:
    helix: { category: case-hits }
    base-cards: { name: "Base Set" }
    topps-chrome-radiating-rookies: { tier: short-print }   # also moves it from Case Hits to Inserts
    some-section-id: { hidden: true }
```

The key on the left is the **section ID**. The easiest way to get it is to copy it from the `id`
column of the report's Sections table, or run `make ids SLUG=<slug>` after a build. You can also
see it in the address bar when you open the section on the site (`#/<slug>/<tab>/<section-id>`).

Section IDs are made from the checklist name: lowercase letters and digits are kept, apostrophes
are dropped, `&` becomes `and`, accents are removed (`é` becomes `e`), and every other run of
spaces or punctuation becomes one hyphen. So `BASE CARDS` becomes `base-cards` and
`2025 MLB COMMISSIONER'S TROPHY` would become `2025-mlb-commissioners-trophy`. If two sections
end up with the same ID, the second gets `-2`, the third `-3`, and so on.

| Option | Allowed values | Effect |
|---|---|---|
| `category` | `base`, `inserts`, `case-hits`, `autographs`, `relics` | Which tab the section appears in. Always wins over the automatic choice |
| `tier` | `common`, `short-print`, `case-hit`, `ultra` | The rarity badge (`short-print` is shown as **Uncommon**). For an insert it also picks the tab: `case-hit` and `ultra` go to **Case Hits**, `common` and `short-print` to **Inserts**, unless you also set `category` |
| `kind` | `base`, `variation`, `insert`, `autograph`, `relic`, `autograph-relic` | What type of section it is |
| `name` | any text | The display name on the site (the report keeps the checklist name) |
| `hidden` | `true` | Hide the section from the site. The report still lists it, marked `(hidden)` |

To move a section to another tab, set `category`.

How tabs are picked automatically:

- Base cards and variations (including Super Short Prints) go in **Base & Parallels**.
- Autographs go in **Autographs**, and relics and autograph relics go in **Relics**.
- Inserts go in **Case Hits** if their tier is `case-hit` or `ultra`, which means rarer than about
  one per case in the primary format. Every other insert goes in **Inserts**.

### 5C. Rarity thresholds (optional)

Tiers are measured in packs per card, using the primary format's box configuration (step 6):

| Tier | Badge on the site | Meaning | Hobby 20 packs × 12 boxes |
|---|---|---|---|
| `common` | Common | at least one per box | up to 1:20 |
| `short-print` | Uncommon | at least one per case | up to 1:240 |
| `case-hit` | Case Hit | up to one per 10 cases | up to 1:2,400 |
| `ultra` | Ultra | rarer than that | beyond 1:2,400 |

The `short-print` tier is shown as **Uncommon**: collectors read "SP" as a deliberately short-printed
card, and most sections in this band (e.g. Rookie Autographs at 1:46) aren't.

To change the cut-offs for a set, set them in packs:

```yaml
tiers:
  commonMax: 20
  shortPrintMax: 240
  caseHitMax: 2400
```

## 6. Box and case configuration

`make new` lists every format (odds column) it found in the odds PDF under `formats:`. Fill in the
box configuration so the site can show "≈ 1 per N boxes / cases" and work out rarity tiers:

```yaml
primaryFormat: hobby
formats:
  hobby:           { label: Hobby, packsPerBox: 20, boxesPerCase: 12 }
  jumbo:           { label: Jumbo, packsPerBox: null, boxesPerCase: null }
  breaker-delight: { label: "Breaker's Delight" }
```

- **Keep the IDs on the left** (`hobby`, `jumbo`, `breaker-delight`, …) exactly as generated,
  because they come from the odds PDF's columns. Only edit what's inside `{ … }`.
- `label`: the name shown in the site's format picker.
- `packsPerBox` and `boxesPerCase`: take these from the product's sell sheet or the box itself.
  Leave them as `null` (or leave them out) if you don't know them. The site then shows pack odds only.
- `primaryFormat`: the format used to decide rarity tiers, and therefore what counts as a Case Hit.
  It defaults to the first column, which is usually Hobby. If a section isn't sold in the primary
  format, its tier comes from the format where it's most common.
- If the primary format's box configuration is unknown, tiers assume 20 packs per box and 12 boxes per case.

## 7. Example card images (optional)

Without images, hovering a parallel shows a generated card in that parallel's colour and finish
(gold, refractor sheen, wave, superfractor, …). To show a real example, put image files in
`sets/<slug>/images/` (create the folder) and name them like this:

| File name | Used for |
|---|---|
| `base-cards--gold-refractor.jpg` | The Gold Refractor of **Base Cards** only (`<section-id>--<parallel-id>`, with **two** hyphens) |
| `gold-refractor.jpg` | The Gold Refractor of **every** section that has one, unless a more specific image exists (`<parallel-id>`) |
| `base-cards.jpg` | The base version of **Base Cards** (`<section-id>`) |

- Allowed extensions are `.jpg`, `.jpeg`, `.png`, `.webp`, `.avif` and `.gif`.
- **To get the exact names, run `make ids SLUG=<slug>`** after a build. It lists every section ID
  and, under it, `<section-id>--<parallel-id>` for each of its parallels. Add the extension and
  that's the file name.
- The **parallel ID** is made from the parallel's name the same way as section IDs (step 5B):
  `Gold Refractor` becomes `gold-refractor` and `Gold RayWave Refractor` becomes `gold-raywave-refractor`.

You can also point to images from `set.yaml`. This is handy for a file with a different name, or an
image hosted online (`https://` only):

```yaml
images:
  "base-cards/gold-refractor": my-gold-scan.jpg        # file in sets/<slug>/images/
  "*/superfractor": https://example.com/superfractor.jpg
```

For a parallel, the first match in this order wins:

1. a `set.yaml` entry `"<section-id>/<parallel-id>"`
2. a file `<section-id>--<parallel-id>.*`
3. a `set.yaml` entry `"*/<parallel-id>"`
4. a file `<parallel-id>.*`

For a section's base version, use the entry `"<section-id>"` or the file `<section-id>.*`.

`make build` copies the images into `site/data/<slug>/images/`, and the report's **Images** section
shows where each one went (and flags any file that matched nothing as **unused**). Keep them small
(around 600 px wide and under 200 KB), and only use your own scans or photos, or images you have
permission to use.

## 8. Preview locally

```sh
make build
make serve
```

Open <http://localhost:8765/#/2027-topps-chrome-baseball>. Click through every tab, hover a few
parallel chips, switch formats in the format picker and try the search. Press `Ctrl+C` in Terminal
to stop the server. If the page looks out of date, hard-refresh with `Cmd+Shift+R`.

## 9. Publish

First run the same checks the deploy runs:

```sh
make check
```

This runs the unit tests and then builds every set. (`make test` on its own doesn't build your new
set, so it can pass even when your `set.yaml` is broken.) Before you push, make sure that:

- the tests end with `OK`;
- every set prints its summary line, and nothing says `FAILED` or shows a Python error (`Traceback`);
- `make` doesn't end with `make: *** … Error`;
- your set's summary says `0 unmatched`, or you've read the remaining unmatched rows in the report
  and decided to leave them.

Then publish:

```sh
git add sets/2027-topps-chrome-baseball
git commit -m "Add 2027 Topps Chrome Baseball"
git push
```

GitHub Actions rebuilds the data from the PDFs and deploys the site, usually within a couple of
minutes. Watch it on the repo's **Actions** tab
(<https://github.com/brand1345/topps-checklists/actions>). A green check means the site is live at
<https://brand1345.github.io/topps-checklists/>. A red X means a step failed and the live site still
shows the previous version, so open the run to see which step it was. The live site is always rebuilt
from `sets/`, so that folder is what matters. If `git status` also shows changes under `site/data/`
or `reports/`, committing them is harmless.

**Topps updated the PDFs?** Replace `sets/<slug>/checklist.pdf` or `odds.pdf` with the new file,
keeping the same file name. Then run `make build`, re-read the report, run `make check`, and commit
and push. Your `set.yaml` fixes still apply.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Python not found at '.venv/bin/python'` | Run `make setup`. |
| `SLUG, CHECKLIST and ODDS are required` | `make new` needs all three; check spelling and capitals. |
| "No such file" for a PDF | The path is wrong. Type `ODDS=` and drag the file into Terminal, without adding quotes. If you type the path yourself and it has spaces, put it in double quotes instead. |
| `new failed: … set.yaml already exists` | That slug already exists in `sets/`. Pick another slug, or delete the old `sets/<slug>/` folder first. |
| `new failed: invalid slug` | Use only lowercase letters, digits and single hyphens, e.g. `2027-topps-chrome-baseball`. |
| `[<slug>] FAILED: …` when building | Read the rest of the line. For a `set.yaml` problem it names the line; fix it and run `make build` again. If it says it's a pipeline bug, report it with the two PDFs. |
| A YAML error when building | Check the indentation (spaces only) and quoting in `set.yaml` near the line it mentions. |
| A whole PDF parses badly | Run `make inspect PDF=sets/<slug>/checklist.pdf`. For a checklist it shows the column boundaries and each section with its card count; add `ARGS=--cards` to list every card, or `ARGS=--lines` to see every line and how it was read. For `odds.pdf` it shows the formats and every row with its values. Include the output when reporting the problem. |
| An odds value looks wrong (`1:1,2175`) | Topps printed it that way. It's kept as-is and flagged on purpose (see step 4). |
| A removed or renamed set still shows locally | Run `make build` without `SLUG`. A full build deletes the generated files of any set whose folder is gone from `sets/`. Commit those deletions along with the change to `sets/`. |
