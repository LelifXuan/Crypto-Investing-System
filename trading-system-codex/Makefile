.PHONY: install dev dev-local db-up db-down migrate test lint check clean tidy-history release-zip

install:
	python -m pip install -e .[dev]

dev:
	python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

dev-local:
	python -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

migrate:
	python -m alembic upgrade head

test:
	python -m pytest -q

lint:
	python -m ruff check .

check: lint
	python -m pytest -q
	python -m compileall app tests scripts/tasks.py
	python -c "import app.main"
	node --check app/static/main.js
	node --check app/static/core/api.js
	node --check app/static/core/dom.js
	node --check app/static/pages/structure.js

clean:
	python scripts/clean_workspace.py

tidy-history:
	python scripts/normalize_historical_data.py

release-zip:
	python scripts/create_release_zip.py
