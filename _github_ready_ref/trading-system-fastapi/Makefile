.PHONY: install dev db-up db-down migrate test lint check clean release-zip

install:
	pip install -e .[dev]

dev:
	uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

migrate:
	alembic upgrade head

test:
	pytest -q

lint:
	ruff check .

check: lint
	pytest -q
	python -m compileall app tests

clean:
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov coverage.xml dist

release-zip:
	python scripts/create_release_zip.py
