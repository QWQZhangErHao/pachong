.PHONY: help install dev-install test lint fmt clean migrate

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	uv pip install -e .

dev-install: ## Install with dev dependencies
	uv pip install -e ".[dev]"

test: ## Run tests
	pytest -v

lint: ## Lint with ruff
	ruff check pachong/ tests/

fmt: ## Format with ruff
	ruff format pachong/ tests/

migrate: ## Run Alembic migrations
	alembic upgrade head

migration: ## Create new Alembic migration (usage: make migration M="description")
	alembic revision --autogenerate -m "$(M)"

clean: ## Clean build artifacts
	rm -rf dist/ build/ *.egg-info/ __pycache__/ .pytest_cache/ .mypy_cache/ .ruff_cache/

worker: ## Start a worker process
	python -m pachong.cli.worker

scheduler: ## Start the scheduler process
	python -m pachong.cli.scheduler

api: ## Start the API server
	uvicorn pachong.api.app:app --reload
