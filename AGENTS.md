# Repository Guidelines

## Project Structure & Module Organization

`app/main.py` creates the FastAPI application. HTTP routes live in `app/api/v1/`; request and response schemas are in `app/schemas/`. Keep database models in `app/models/`, business logic in `app/services/`, and OCR/background jobs in `app/worker/`. Alembic configuration and revisions live in `app/db/` and `alembic.ini`. Tests are in `tests/test_*.py`, with shared fixtures in `tests/conftest.py`. Local document data belongs in the ignored `data/` directory.

## Build, Test, and Development Commands

- `docker compose up --build`: build and start PostgreSQL, Redis, the API, and the worker; the API listens on port 8000.
- `pip install -r requirements.txt`: install runtime dependencies for local development. Install the `dev` extras from `pyproject.toml` for pytest, Ruff, and mypy.
- `alembic upgrade head`: apply database migrations against `DATABASE_URL`.
- `uvicorn app.main:application --reload --port 8000`: run the API locally after configuring PostgreSQL and Redis.
- `arq app.worker.settings.WorkerSettings`: run OCR jobs in a separate terminal.
- `python -m pytest tests/ -v`: run the test suite. `ruff check app/ tests/` and `mypy app/` run the configured quality checks.

## Coding Style & Naming Conventions

Use four-space indentation, Python type hints, `snake_case` for modules and functions, and `PascalCase` for classes. Place new routes, schemas, and service logic in their matching packages. Ruff uses a 100-character line limit; mypy runs in strict mode for Python 3.13. Run both checks before opening a pull request.

## Testing Guidelines

Use pytest and httpx for API tests. Name test files `test_*.py` and test functions `test_*`; add focused cases for new routes, service behavior, and migrations. **Use a disposable PostgreSQL database for tests:** the session fixture in `tests/conftest.py` drops and recreates its `public` schema. No coverage threshold is configured.

## Commit & Pull Request Guidelines

Recent commits use short, imperative subjects such as `Fix docker-compose: ...`; follow that pattern and keep each commit focused. In pull requests, describe the behavior changed, link the relevant issue when one exists, and report test and lint results. Include API examples or screenshots when they clarify externally visible changes.

## Configuration & Security

Copy `.env.example` to `.env` and adjust service URLs for your setup. Docker Compose publishes PostgreSQL on host port 5433, while `.env.example` uses 5432. Keep secrets and uploaded documents out of Git; `.env` and `data/` are ignored.
