.PHONY: test run docker-build lint

test:
	python -m pytest -v --tb=short

run:
	python -m src.main

docker-build:
	docker compose build

lint:
	python -m ruff check src/ tests/ || true