.PHONY: install test lint typecheck secrets check smoke run

install:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -e ".[dev]"

test:
	. .venv/bin/activate && pytest -q

lint:
	. .venv/bin/activate && ruff check agenticapi tests

typecheck:
	. .venv/bin/activate && mypy agenticapi

secrets:
	. .venv/bin/activate && python scripts/check_secrets.py

check: lint typecheck test secrets

smoke:
	. .venv/bin/activate && python -m agenticapi run --config configs/smoke.json --label smoke

run:
	. .venv/bin/activate && python -m agenticapi run --config configs/default.json --label full
