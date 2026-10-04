# Topps Checklists — common tasks. Run `make` (or `make help`) for the list.
#
# Everything runs through the project virtualenv in .venv/ (create it with `make setup`).
# Override the interpreter with `make build PY=python3` if you manage Python yourself.

PYTHON3 ?= python3
VENV    := .venv
PY      ?= $(VENV)/bin/python
PORT    ?= 8765
ARGS    ?=
FIXTURES_OUT     := fixtures/_out
FIXTURES_REPORTS := fixtures/_reports

# Only honour NAME when it is given on the make command line: some environments
# (e.g. WSL) export $NAME as the machine's hostname, which must not leak into `make new`.
ifneq ($(origin NAME),command line)
NAME :=
endif

# Single-quote a value for /bin/sh so paths with spaces, parentheses or quotes survive.
shq = '$(subst ','\'',$(1))'

NEW_USAGE := make new SLUG=2027-topps-chrome-baseball CHECKLIST=~/Downloads/checklist.pdf [ODDS=~/Downloads/odds.pdf] [NAME="2027 Topps Chrome Baseball"]

.DEFAULT_GOAL := help
.PHONY: help setup build test check serve new inspect ids fixtures clean check-py

help:
	@echo "Topps Checklists"
	@echo ""
	@echo "  make setup      Create .venv/ and install requirements.txt"
	@echo "  make build      Parse every set in sets/ -> site/data/*.json + reports/*.md"
	@echo "                  (one set only: make build SLUG=2026-topps-chrome-baseball)"
	@echo "  make test       Run the unit tests"
	@echo "  make check      Run the tests, then build every set, as the deploy does (run it before git push)"
	@echo "  make serve      Preview the site at http://localhost:$(PORT)/"
	@echo "  make new        Scaffold a new set from its two Topps PDFs:"
	@echo '                    $(NEW_USAGE)'
	@echo "  make inspect    Debug dump of what the parser sees in one PDF:"
	@echo "                    make inspect PDF=sets/<slug>/checklist.pdf [ARGS=--cards]"
	@echo "                  (ARGS takes the 'inspect' flags: --cards, --lines, --kind checklist|odds)"
	@echo "  make ids        List section ids and image names for a built set: make ids SLUG=<slug>"
	@echo "  make fixtures   Build every product in fixtures/ -> $(FIXTURES_OUT)/ + $(FIXTURES_REPORTS)/"
	@echo "  make clean      Delete generated data, reports and caches"

setup:
	test -x $(VENV)/bin/python || $(PYTHON3) -m venv $(VENV)
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -r requirements.txt

# Friendly error instead of "No such file or directory" when the venv is missing.
check-py:
	@command -v $(PY) >/dev/null 2>&1 || { echo "Python not found at '$(PY)'. Run 'make setup' first." >&2; exit 1; }

build: check-py
	$(PY) -m pipeline build $(SLUG)

test: check-py
	$(PY) -m unittest discover -s tests -v

# The same two steps the GitHub Actions deploy runs, in the same order. If this passes
# locally, the deploy's test and build steps will pass too.
check: test build

serve:
	@echo "Serving site/ at http://localhost:$(PORT)/  (Ctrl+C to stop)"
	$(PYTHON3) -m http.server $(PORT) -d site

# Each PDF path is cleaned up before it reaches the pipeline:
# - `~/` is expanded here because zsh (the macOS default shell) does not expand it after `VAR=`;
# - a file dragged from Finder into Terminal arrives with backslash escapes (`Odds\ \(1\).pdf`).
#   Inside quotes the shell keeps those backslashes, so when the path as given does not exist,
#   the same path with the backslashes removed is tried.
new: check-py
	$(if $(and $(SLUG),$(CHECKLIST)),,$(error SLUG and CHECKLIST are required. Usage: $(NEW_USAGE)))
	@resolve() { \
	  p=$$1; \
	  case "$$p" in "~/"*) p="$$HOME/$${p#??}";; esac; \
	  if [ ! -e "$$p" ]; then \
	    q=$$(printf '%s\n' "$$p" | sed 's/\\\(.\)/\1/g'); \
	    case "$$q" in "~/"*) q="$$HOME/$${q#??}";; esac; \
	    if [ -e "$$q" ]; then p=$$q; fi; \
	  fi; \
	  printf '%s\n' "$$p"; \
	}; \
	checklist=$$(resolve $(call shq,$(CHECKLIST))); \
	$(if $(ODDS),odds=$$(resolve $(call shq,$(ODDS))); ,)\
	set -x; \
	$(PY) -m pipeline new $(call shq,$(SLUG)) --checklist "$$checklist" $(if $(ODDS),--odds "$$odds") $(if $(NAME),--name $(call shq,$(NAME)))

# ARGS is passed through unquoted so it can hold several flags, e.g. ARGS="--kind checklist --cards".
inspect: check-py
	$(if $(PDF),,$(error Usage: make inspect PDF=sets/<slug>/checklist.pdf [ARGS=--cards]))
	$(PY) -m pipeline inspect $(if $(strip $(ARGS)),$(strip $(ARGS)) )$(call shq,$(PDF))

# Reads the built site/data/<slug>.json, so run `make build` first. Prints every section id
# (the key for set.yaml overrides and the `<section-id>.jpg` image name) and, under it, the
# `<section-id>--<parallel-id>` image name of each of its parallels.
ids: check-py
	$(if $(SLUG),,$(error Usage: make ids SLUG=<slug>  (after make build)))
	@test -f $(call shq,site/data/$(SLUG).json) || { echo "site/data/$(SLUG).json not found. Run 'make build SLUG=$(SLUG)' first." >&2; exit 1; }
	@printf '%s\n' \
	  'import json, sys' \
	  'data = json.load(open(sys.argv[1], encoding="utf-8"))' \
	  'print("%-58s %s" % ("SECTION ID / IMAGE NAME (without extension)", "NAME ON THE SITE"))' \
	  'for s in data["sections"]:' \
	  '    print("%-58s %s" % (s["id"], s["name"]))' \
	  '    for p in s["parallels"]:' \
	  '        print("  %-56s %s" % (s["id"] + "--" + p["id"], p["name"]))' \
	| $(PY) - $(call shq,site/data/$(SLUG).json)

# fixtures/ is local-only (gitignored): one folder per Topps product holding checklist.pdf
# and/or odds.pdf, built exactly like sets/ (folders starting with _ or . are skipped). Data
# goes to fixtures/_out/ and reports to fixtures/_reports/. The build skips a folder with no
# checklist PDF, so each PDF in such a folder is run through `pipeline inspect` instead
# (fixtures/_reports/<folder>--<pdf>.txt). Exits non-zero if anything failed.
fixtures: check-py
	@test -d fixtures || { echo "No fixtures/ folder (it is local-only and gitignored)." >&2; exit 1; }
	@mkdir -p $(FIXTURES_OUT) $(FIXTURES_REPORTS); status=0; \
	echo "$(PY) -m pipeline build --sets-dir fixtures --out-dir $(FIXTURES_OUT) --reports-dir $(FIXTURES_REPORTS)"; \
	$(PY) -m pipeline build --sets-dir fixtures --out-dir $(FIXTURES_OUT) --reports-dir $(FIXTURES_REPORTS) || status=1; \
	for dir in fixtures/*/; do \
	  name=$$(basename "$$dir"); \
	  case "$$name" in _*) continue;; esac; \
	  set -- "$$dir"*[Cc]hecklist*.pdf; [ -f "$$1" ] && continue; \
	  for pdf in "$$dir"*.pdf; do \
	    [ -f "$$pdf" ] || continue; \
	    out="$(FIXTURES_REPORTS)/$$name--$$(basename "$$pdf" .pdf).txt"; \
	    if $(PY) -m pipeline inspect "$$pdf" > "$$out" 2>&1; then \
	      echo "[$$name] inspected $$pdf -> $$out"; \
	    else \
	      echo "[$$name] inspect FAILED for $$pdf (see $$out)"; status=1; \
	    fi; \
	  done; \
	done; \
	if [ $$status -eq 0 ]; then echo "fixtures: OK"; else echo "fixtures: FAILED (see above)" >&2; fi; \
	exit $$status

clean:
	rm -f site/data/*.json reports/*.md
	rm -rf site/data/*/ $(FIXTURES_OUT) $(FIXTURES_REPORTS)
	find . -path ./$(VENV) -prune -o -name __pycache__ -type d -prune -exec rm -rf {} +
