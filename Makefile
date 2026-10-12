# Convenience targets for Linux/macOS (and Windows with GNU make).
# Every target is a thin wrapper; the commands work on their own too (see README.md).
PY ?= python

.PHONY: install test lint demo daily site e2e dev check

install:            ## install pipeline (editable, with dev tools) and web dependencies
	$(PY) -m pip install -e "pipeline[dev]"
	cd web && npm ci

test:               ## unit tests: pipeline + web
	cd pipeline && $(PY) -m pytest
	cd web && npm test

lint:               ## lint + type-check: pipeline + web
	cd pipeline && $(PY) -m ruff check . && $(PY) -m ruff format --check . && $(PY) -m mypy
	cd web && npm run lint && npm run typecheck

demo:               ## 30 stocks end to end (< 5 minutes) into web/public/data
	$(PY) -m convergealpha demo

daily:              ## full pipeline locally against ./data (a clone of the private data repo)
	cd pipeline && $(PY) -m convergealpha daily --data ../data --out ../web/public/data

site: demo          ## build the production website with fresh local data
	cd web && npm run build

e2e: site           ## phone + desktop browser tests against the built site
	cd web && npm run e2e

dev: demo           ## local dev server at http://localhost:5173
	cd web && npm run dev

check: lint test e2e
