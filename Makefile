VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
SKILL_VAULT := $(VENV)/bin/skill-vault

.PHONY: install init migrate seed lint format typecheck test check serve web mcp cov

.venv:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

install: .venv

init:
	$(PYTHON) -m skill_vault.cli init

migrate:
	$(PYTHON) -m skill_vault.cli migrate

seed:
	$(PYTHON) -m skill_vault.cli seed

serve:
	$(SKILL_VAULT) serve --transport streamable-http

mcp:
	$(SKILL_VAULT) serve --transport streamable-http

web:
	$(SKILL_VAULT) web

lint:
	$(VENV)/bin/ruff check .

format:
	$(VENV)/bin/ruff format .

format-check:
	$(VENV)/bin/ruff format --check .

typecheck:
	$(PYTHON) -m mypy skill_vault

test:
	$(VENV)/bin/pytest

cov:
	$(VENV)/bin/pytest tests/ --cov=skill_vault --cov-report=term-missing

check: lint format-check typecheck
