.PHONY: help dev migrate test test-unit test-gate eval lint format typecheck check up down logs ps clean frontend-dev frontend-build

# Keep Compose and the backend on the same env file. Fall back to .env.example
# so `make up` still works before the first `cp .env.example .env`.
COMPOSE_ENV := $(if $(wildcard .env),.env,.env.example)
COMPOSE := docker compose --env-file $(COMPOSE_ENV) -f infra/docker-compose.yml

help:
	@echo "Available commands:"
	@echo "  make dev            - Run FastAPI development server with auto-reload"
	@echo "  make frontend-dev   - Run React Vite development server (port 3000)"
	@echo "  make frontend-build - Build production frontend bundle"
	@echo "  make test           - Run all unit and CI eval gate tests"
	@echo "  make test-gate      - Run CI evaluation gate against golden dataset"
	@echo "  make eval           - Clean-ingest into an isolated DB/collection and score the golden test split"
	@echo "  make lint           - Run Ruff linter"
	@echo "  make format         - Run Ruff code formatter"
	@echo "  make typecheck      - Run Mypy static type checker"
	@echo "  make check          - Run all checks (lint, format-check, typecheck, test)"
	@echo "  make up             - Start local infrastructure (fails if POSTGRES_PORT is not Docker Postgres)"
	@echo "  make migrate        - Apply Alembic migrations to PostgreSQL"
	@echo "  make down           - Stop local infrastructure"
	@echo "  make logs           - Tail docker infrastructure logs"
	@echo "  make ps             - Show status of infrastructure containers"
	@echo "  make clean          - Remove temporary and cache files"

dev: migrate
	uv run --directory backend uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

test:
	uv run --directory backend pytest -v

test-gate:
	uv run --directory backend pytest tests/eval_gate/test_eval_gate.py -v

test-unit:
	uv run --directory backend pytest tests/unit -v

test-int:
	uv run --directory backend pytest tests/integration -v -m integration

worker:
	uv run --directory backend python -m app.indexing.outbox_worker

migrate:
	uv run --directory backend alembic upgrade head

ingest: migrate
	uv run --directory backend python -m app.ingestion.cli

reconcile: migrate
	uv run --directory backend python -m app.indexing.reconciler $(if $(REPAIR),--repair,)

# Isolated evaluation: dedicated PostgreSQL DB + Qdrant collection, clean ingest,
# then the golden test split. Extra flags: SPLIT=dev|test|all BUDGET_USD=0.50
eval:
	uv run --directory backend python -m app.tools.eval_cli \
		--split $(or $(SPLIT),test) \
		$(if $(BUDGET_USD),--budget-usd $(BUDGET_USD),) \
		$(if $(CONCURRENCY),--concurrency $(CONCURRENCY),) \
		$(if $(JSON_REPORT),--json-report $(JSON_REPORT),)


lint:
	uv run --directory backend ruff check app tests

format:
	uv run --directory backend ruff format app tests

typecheck:
	uv run --directory backend mypy app tests

check: lint typecheck test
	uv run --directory backend ruff format --check app tests

up:
	uv run --directory backend python -m app.tools.preflight_postgres
	$(COMPOSE) up -d --wait

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
