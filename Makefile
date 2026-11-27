.PHONY: help dev migrate test test-unit eval eval-compare calibrate-judge lint format typecheck check up down logs ps clean frontend-dev frontend-build

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
	@echo "  make eval           - Clean-ingest into an isolated DB/collection and score the golden test split"
	@echo "  make eval-compare   - Run dense/sparse/hybrid/full/graph_forced on the same split and print one comparison table"
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

# `make dev` intentionally targets the developer stores, so opt in to writes here.
# Isolated test/eval runs use a separate shell environment instead.
dev: migrate
	GRAPHRAG_ALLOW_DEV_WRITES=1 uv run --directory backend uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

test:
	uv run --directory backend pytest -v

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
# then the golden test split. Extra flags: SPLIT=dev|test|all CONFIG=dense|sparse|hybrid|full|graph_forced
# BUDGET_USD=0.50 CONCURRENCY=2 JSON_REPORT=path JUDGE=1 JUDGE_MODEL=... JUDGE_THRESHOLD=0.5
eval:
	uv run --directory backend python -m app.tools.eval_cli \
		--config $(or $(CONFIG),full) \
		--split $(or $(SPLIT),test) \
		$(if $(BUDGET_USD),--budget-usd $(BUDGET_USD),) \
		$(if $(CONCURRENCY),--concurrency $(CONCURRENCY),) \
		$(if $(FRESH_LLM_CACHE),--fresh-llm-cache,) \
		$(if $(filter 1 true yes,$(JUDGE)),--judge,) \
		$(if $(JUDGE_MODEL),--judge-model $(JUDGE_MODEL),) \
		$(if $(JUDGE_THRESHOLD),--judge-threshold $(JUDGE_THRESHOLD),) \
		$(if $(JSON_REPORT),--json-report $(JSON_REPORT),)

# Honest baseline: same corpus, prompt, model, and split; five retrieval configs
# with a cold per-config LLM cache. Extra flags: SPLIT=... BUDGET_USD=... JSON_DIR=...
# JUDGE=1 JUDGE_MODEL=... JUDGE_THRESHOLD=0.5
eval-compare:
	uv run --directory backend python -m app.tools.eval_compare \
		--split $(or $(SPLIT),test) \
		$(if $(BUDGET_USD),--budget-usd $(BUDGET_USD),) \
		$(if $(CONCURRENCY),--concurrency $(CONCURRENCY),) \
		$(if $(filter 1 true yes,$(JUDGE)),--judge,) \
		$(if $(JUDGE_MODEL),--judge-model $(JUDGE_MODEL),) \
		$(if $(JUDGE_THRESHOLD),--judge-threshold $(JUDGE_THRESHOLD),) \
		$(if $(JSON_DIR),--json-dir $(JSON_DIR),)

# Calibrate the LLM judge on 30 hand-labelled answers and write
# evals/calibration/judge_agreement.json for the comparison report.
calibrate-judge:
	uv run --directory backend python -m app.tools.calibrate_judge \
		$(if $(JUDGE_MODEL),--judge-model $(JUDGE_MODEL),) \
		$(if $(JUDGE_THRESHOLD),--judge-threshold $(JUDGE_THRESHOLD),) \
		--write


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
