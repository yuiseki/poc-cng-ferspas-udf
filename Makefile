PY := .venv/bin/python
PORT ?= 8811

.PHONY: help install test serve viewer tile

help:
	@echo "make install  create .venv from the lockfile"
	@echo "make test     unit tests"
	@echo "make serve    run the tile server on :$(PORT)"
	@echo "make tile     fetch one tile as a smoke test"

install:
	uv sync
	uv pip install -e .

test:
	$(PY) -m pytest -q

serve:
	$(PY) -m uvicorn ferspas_tile.app:app --host 127.0.0.1 --port $(PORT) --app-dir src

tile:
	curl -sS -o /tmp/ferspas-tile.png -w 'HTTP %{http_code} %{size_download}B %{time_total}s\n' \
	  "http://127.0.0.1:$(PORT)/tiles/AGERA5-PF/2026-08-01/2/1/1.png"
	@file /tmp/ferspas-tile.png
