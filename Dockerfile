# Reproducible image for the Pulse event-scraping pipeline (Playwright + Python).
FROM python:3.12-slim

# uv for fast, locked installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first for better layer caching (uses the committed lockfile).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Chromium + its system libraries (Playwright). Only Chromium to keep the image small.
RUN uv run playwright install --with-deps chromium

# Application code
COPY main.py ./
COPY scrapers ./scrapers
COPY pipeline ./pipeline
COPY db ./db

# Default: run the full pipeline. Override for a single scraper:
#   docker run --env-file .env pulse-pipeline uv run python main.py --run kulturdaten
CMD ["uv", "run", "python", "main.py", "--run-all"]
