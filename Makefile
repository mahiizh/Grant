.PHONY: help dev test test-unit test-gate lint format typecheck check up down logs ps clean frontend-dev frontend-build

help:
	@echo "Available commands:"
	@echo "  make dev            - Run FastAPI development server with auto-reload"
	@echo "  make frontend-dev   - Run React Vite development server (port 3000)"
	@echo "  make frontend-build - Build production frontend bundle"
	@echo "  make test           - Run all unit and CI eval gate tests"
	@echo "  make test-gate      - Run CI evaluation gate against golden dataset"
	@echo "  make lint           - Run Ruff linter"
	@echo "  make format         - Run Ruff code formatter"
	@echo "  make typecheck      - Run Mypy static type checker"
	@echo "  make check          - Run all checks (lint, format-check, typecheck, test)"
	@echo "  make up             - Start local infrastructure (Postgres, Qdrant, Neo4j, Redis)"
	@echo "  make down           - Stop local infrastructure"
	@echo "  make logs           - Tail docker infrastructure logs"
	@echo "  make ps             - Show status of infrastructure containers"
	@echo "  make clean          - Remove temporary and cache files"

dev:
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

ingest:
	uv run --directory backend python -m app.ingestion.cli

reconcile:
	uv run --directory backend python -m app.indexing.reconciler $(if $(REPAIR),--repair,)


lint:
	uv run --directory backend ruff check app tests

format:
	uv run --directory backend ruff format app tests

typecheck:
	uv run --directory backend mypy app tests

check: lint typecheck test
	uv run --directory backend ruff format --check app tests

up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

logs:
	docker compose -f infra/docker-compose.yml logs -f

ps:
	docker compose -f infra/docker-compose.yml ps

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
