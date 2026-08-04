init:
	python -m skill_vault.cli init

migrate:
	python -m skill_vault.cli migrate

seed:
	python -m skill_vault.cli seed

lint:
	ruff check .

format:
	ruff format .

typecheck:
	python -m mypy skill_vault

test:
	pytest

check: lint typecheck
