# ConvergeAlpha pipeline

Python 3.12 package that ingests data, computes features and forecasts, and exports the JSON
files the website reads.

```bash
pip install -e ".[dev]"
python -m convergealpha daily --out ../site-data   # run every implemented step
python -m convergealpha health --out ../site-data  # only write health.json
pytest && ruff check . && mypy
```

See `../PROGRESS.md` for what each phase implements.
