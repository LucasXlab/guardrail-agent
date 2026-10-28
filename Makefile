PYTHON ?= python3
VENV ?= .venv
BIN = $(VENV)/bin

.PHONY: dev lint test build check demo
dev:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install --disable-pip-version-check -e ".[dev]"

lint:
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

test:
	$(BIN)/python -m pytest --cov=guardrail_agent --cov-report=term-missing --cov-report=json --cov-fail-under=70

build:
	$(BIN)/python -m build --no-isolation

check: lint test build

demo:
	$(BIN)/python scripts/demo.py
