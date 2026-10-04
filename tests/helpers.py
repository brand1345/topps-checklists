import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_2026 = os.path.join(ROOT, "sets", "2026-topps-chrome-baseball")
CHECKLIST_2026 = os.path.join(SET_2026, "checklist.pdf")
ODDS_2026 = os.path.join(SET_2026, "odds.pdf")
FIXTURES = os.path.join(ROOT, "fixtures")

_cache = {}


def parsed_checklist_2026():
    if "cl" not in _cache:
        from pipeline.checklist import parse_checklist
        _cache["cl"] = parse_checklist(CHECKLIST_2026)
    return _cache["cl"]


def parsed_odds_2026():
    if "od" not in _cache:
        from pipeline.odds import parse_odds
        _cache["od"] = parse_odds(ODDS_2026)
    return _cache["od"]


FROZEN_YAML_2026 = os.path.join(ROOT, "tests", "data", "2026-topps-chrome-baseball.set.yaml")


def built_2026():
    """Build the real PDFs once per test run, with a frozen copy of set.yaml (tests/data/), so
    editing the live sets/<slug>/set.yaml can't break the tests."""
    if "build" not in _cache:
        import shutil
        import tempfile
        from pipeline.build import build_set
        tmp = tempfile.mkdtemp(prefix="tc-build-")
        set_dir = os.path.join(tmp, "sets", "2026-topps-chrome-baseball")
        os.makedirs(set_dir)
        for fn in ("checklist.pdf", "odds.pdf"):
            shutil.copy(os.path.join(SET_2026, fn), os.path.join(set_dir, fn))
        shutil.copy(FROZEN_YAML_2026, os.path.join(set_dir, "set.yaml"))
        data, report, summary = build_set(set_dir, os.path.join(tmp, "data"), os.path.join(tmp, "reports"),
                                          now="2026-01-01T00:00:00Z")
        _cache["build"] = (data, report, summary, tmp)
    return _cache["build"]


def built_2026_live():
    """Build sets/2026-topps-chrome-baseball exactly as `make build` does (live set.yaml)."""
    if "build_live" not in _cache:
        import tempfile
        from pipeline.build import build_set
        tmp = tempfile.mkdtemp(prefix="tc-build-live-")
        _cache["build_live"] = build_set(SET_2026, os.path.join(tmp, "data"), os.path.join(tmp, "reports"),
                                         now="2026-01-01T00:00:00Z")
    return _cache["build_live"]
