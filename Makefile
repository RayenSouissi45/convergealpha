# Convenience targets for Linux/macOS (and Windows with GNU make).
# Every target is a thin wrapper; the commands work on their own too (see README.md).
PY ?= python

.PHONY: install test lint daily site e2e dev check

install:            ## install pipeline (editable, with dev tools) and web dependencies
	$(PY) -m pip install -e "pipeline[dev]"
	cd web && npm ci

test:               ## unit tests: pipeline + web
	cd pipeline && $(PY) -m pytest
	cd web && npm test

lint:               ## lint + type-check: pipeline + web
	cd pipeline && $(PY) -m ruff check . && $(PY) -m ruff format --check . && $(PY) -m mypy
	cd web && npm run lint && npm run typecheck

daily:              ## run the pipeline locally; output goes where the website reads it
	cd pipeline && $(PY) -m convergealpha daily --out ../web/public/data

site: daily         ## build the production website with fresh local data
	cd web && npm run build

e2e: site           ## phone + desktop browser tests against the built site
	cd web && npm run e2e

dev: daily          ## local dev server at http://localhost:5173
	cd web && npm run dev

check: lint test e2e
