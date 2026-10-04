"""CLI: python -m pipeline build|new|inspect  (see docs/SPEC.md)."""
from __future__ import annotations

import argparse
import json
import os
import sys

from .build import (BuildError, build_set, find_pdfs, looks_like_odds, prune_outputs, scaffold, write_index,
                    write_json_if_changed)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


DEFAULT_SETS_DIR = os.path.abspath(os.path.join(ROOT, "sets"))
DEFAULT_OUT_DIR = os.path.abspath(os.path.join(ROOT, "site", "data"))
DEFAULT_REPORTS_DIR = os.path.abspath(os.path.join(ROOT, "reports"))


def cmd_build(args):
    sets_dir = args.sets_dir
    out_dir = args.out_dir
    reports_dir = args.reports_dir
    if not os.path.isdir(sets_dir):
        print("sets directory not found: %s" % sets_dir, file=sys.stderr)
        return 2
    explicit = bool(args.slugs)
    slugs = args.slugs or sorted(d for d in os.listdir(sets_dir)
                                 if os.path.isdir(os.path.join(sets_dir, d)) and not d.startswith((".", "_")))
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)
    failed = 0
    built = 0
    # Pruning compares out_dir with sets_dir, so only do it when they belong together: building
    # another sets folder (e.g. --sets-dir fixtures) into the default site/data or reports must
    # not delete the real sets' output.
    mismatched = (os.path.abspath(sets_dir) != DEFAULT_SETS_DIR
                  and (os.path.abspath(out_dir) == DEFAULT_OUT_DIR
                       or os.path.abspath(reports_dir) == DEFAULT_REPORTS_DIR))
    if mismatched:
        print("WARNING: --sets-dir is not the default but --out-dir/--reports-dir are; not pruning "
              "old output (pass --out-dir and --reports-dir too)", file=sys.stderr)
    elif not explicit:
        for slug in prune_outputs(sets_dir, out_dir, reports_dir):
            print("[%s] removed generated data: the set folder no longer exists" % slug)
    for slug in slugs:
        set_dir = os.path.join(sets_dir, slug)
        if not os.path.isdir(set_dir):
            print("[%s] no such set directory: %s" % (slug, set_dir), file=sys.stderr)
            failed += 1
            continue
        checklist, odds = find_pdfs(set_dir)
        if not checklist:
            msg = "[%s] skipped: no checklist PDF%s" % (slug, " (odds PDF only)" if odds else "")
            if explicit:
                print(msg.replace("skipped", "FAILED"), file=sys.stderr)
                failed += 1
            else:
                print(msg)
            continue
        try:
            data, report, summary = build_set(set_dir, out_dir, reports_dir)
        except BuildError as exc:
            print("[%s] FAILED: %s" % (slug, exc), file=sys.stderr)
            failed += 1
            continue
        except Exception as exc:  # never let one set stop the others (or the sets.json index)
            print("[%s] FAILED: %s: %s (this is a pipeline bug; please report it with the PDFs)"
                  % (slug, type(exc).__name__, exc), file=sys.stderr)
            failed += 1
            continue
        write_json_if_changed(os.path.join(out_dir, slug + ".json"), data)
        with open(os.path.join(reports_dir, slug + ".md"), "w", encoding="utf-8") as fh:
            fh.write(report)
        built += 1
        print("[%s] %d sections, %d cards (%d RC), %d parallels, odds rows %d: %d matched / %d unmatched, %d warnings"
              % (slug, summary["sections"], summary["cards"], summary["rookies"], summary["parallels"],
                 summary["oddsRows"], summary["matched"], summary["unmatched"], summary["warnings"]))
    index = write_index(out_dir, None if mismatched else sets_dir)
    for slugs_same in index["duplicateNames"]:
        print("WARNING: sets %s have the same name; give each a unique `name:` in its set.yaml"
              % ", ".join(slugs_same), file=sys.stderr)
    print("sets.json: %d set(s) -> %s" % (len(index["sets"]), os.path.join(out_dir, "sets.json")))
    if failed:
        print("%d set(s) failed; see the FAILED lines above" % failed, file=sys.stderr)
    return 1 if failed else 0


def cmd_new(args):
    try:
        path = scaffold(args.sets_dir, args.slug, args.checklist, args.odds, args.name)
    except (BuildError, Exception) as exc:
        print("new failed: %s" % exc, file=sys.stderr)
        return 1
    print("created %s" % path)
    print("Next: edit sets/%s/set.yaml, then run: make build SLUG=%s and read reports/%s.md"
          % (args.slug, args.slug, args.slug))
    return 0


def _looks_like_odds(path):
    return looks_like_odds(path)


def cmd_inspect(args):
    from .checklist import parse_checklist
    from .odds import parse_odds
    path = args.pdf
    kind = args.kind
    if kind == "auto":
        kind = "odds" if _looks_like_odds(path) else "checklist"
    if kind == "odds":
        r = parse_odds(path)
        print("ODDS %s" % path)
        print("title: %s" % r["title"])
        print("first column label: %s   values: %s-aligned" % (r["label"], r["align"]))
        print("formats:")
        for f in r["formats"]:
            print("  %-20s %-20s raw=%r code=%s" % (f["id"], f["label"], f["raw"], f["code"]))
        print("rows (%d):" % len(r["rows"]))
        for row in r["rows"]:
            print("  p%-2d %-70s %s" % (row["page"], row["rawName"], " | ".join(v or "-" for v in row["values"])))
        for w in r["warnings"]:
            print("WARNING: %s" % w)
        return 0
    r = parse_checklist(path)
    d = r["debug"]
    print("CHECKLIST %s" % path)
    print("title: %s" % r["title"])
    print("disclaimer: %s" % r["disclaimer"])
    print("page kinds (M=main, O=overflow/empty): %s" % d["pageKinds"])
    if d["overflowMap"]:
        print("overflow page -> main page: %s" % json.dumps(d["overflowMap"]))
    print("column boundaries: %s  roles: %s" % (d["boundaries"], json.dumps(d["roles"])))
    print("stats: %s" % json.dumps(r["stats"]))
    if args.lines:
        for page in d["pages"]:
            print("--- page %d (%s)" % (page["index"] + 1, page["kind"]))
            for ln in page["lines"]:
                extra = ""
                if ln.cells is not None:
                    extra = "  cells=%s" % json.dumps(ln.cells, ensure_ascii=False)
                print("  %6.1f %-10s %s%s%s" % (ln.top, ln.kind, ln.text, " [RC]" if ln.rookie else "", extra))
    print("sections (%d):" % len(r["sections"]))
    for s in r["sections"]:
        print("  [%s] %s — %d cards / %d rows%s" % (s["group"], s["rawName"], len(s["cards"]), s["rowCount"],
                                                 ("  notes=%s" % s["notes"]) if s.get("notes") else ""))
        if args.cards:
            for c in s["cards"]:
                print("      %-10s %s%s" % (c["code"], " / ".join("%s (%s)%s" % (p["name"], p["team"], " RC" if p["rookie"] else "")
                                                               for p in c["players"]), ""))
    for w in r["warnings"]:
        print("WARNING: %s" % w)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m pipeline", description="Topps checklist/odds PDF pipeline")
    sub = ap.add_subparsers(dest="cmd")
    b = sub.add_parser("build", help="build all (or the listed) sets into site/data + reports")
    b.add_argument("slugs", nargs="*")
    b.add_argument("--sets-dir", default=os.path.join(ROOT, "sets"))
    b.add_argument("--out-dir", default=os.path.join(ROOT, "site", "data"))
    b.add_argument("--reports-dir", default=os.path.join(ROOT, "reports"))
    n = sub.add_parser("new", help="scaffold sets/<slug>/ from two PDFs")
    n.add_argument("slug")
    n.add_argument("--checklist", required=True)
    n.add_argument("--odds")
    n.add_argument("--name")
    n.add_argument("--sets-dir", default=os.path.join(ROOT, "sets"))
    i = sub.add_parser("inspect", help="debug dump of what the parser sees")
    i.add_argument("pdf")
    i.add_argument("--kind", choices=["auto", "checklist", "odds"], default="auto")
    i.add_argument("--lines", action="store_true", help="dump every classified line (checklist)")
    i.add_argument("--cards", action="store_true", help="dump every card (checklist)")
    args = ap.parse_args(argv)
    if args.cmd == "build":
        return cmd_build(args)
    if args.cmd == "new":
        return cmd_new(args)
    if args.cmd == "inspect":
        return cmd_inspect(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
