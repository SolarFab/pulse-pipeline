# Pulse event pipeline — common commands. Run `make help` to list them.
.PHONY: help install lint format typecheck test check scrape run hooks

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install all dependencies (incl. dev) into a locked venv
	uv sync --extra dev

lint:  ## Lint the code (ruff)
	uv run ruff check main.py scrapers pipeline db tests

format:  ## Auto-format the code (ruff)
	uv run ruff format main.py scrapers pipeline db tests
	uv run ruff check --fix main.py scrapers pipeline db tests

test:  ## Run the test suite
	uv run pytest

check: lint test  ## Lint + test (what CI runs)

hooks:  ## Install the pre-commit git hooks
	uv run pre-commit install

scrape:  ## Run the full scraping pipeline
	uv run python main.py --run-all

run:  ## Run a single scraper, e.g. `make run SCRAPER=kulturdaten`
	uv run python main.py --run $(SCRAPER)
