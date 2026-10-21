"""Pytest configuration — session-scoped schema via Alembic."""

import asyncio

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import engine, get_db
from app.core.config import settings
from app.db.base import Base
from app.main import create_app


@pytest.fixture(autouse=True)
def test_api_credentials(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "test-key")
    monkeypatch.setattr(settings, "API_SECRET", "test-secret")


@pytest.fixture(scope="session")
def prepare_database():
    """Clean schema + run Alembic migrations before tests, downgrade after."""
    database_name = make_url(settings.DATABASE_URL).database or ""
    if not database_name.endswith("_test"):
        pytest.fail("DATABASE_URL must target a disposable database ending in _test")

    async def _clean():
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
            await conn.execute(text("GRANT ALL ON SCHEMA public TO pg_database_owner"))
            await conn.execute(text("GRANT ALL ON SCHEMA public TO public"))

    asyncio.run(_clean())

    config = Config("alembic.ini")
    command.upgrade(config, "head")
    yield
    command.downgrade(config, "base")


async def truncate_tables(session: AsyncSession):
    """Truncate all tables for test isolation."""
    for table in reversed(Base.metadata.sorted_tables):
        await session.execute(text(f"TRUNCATE TABLE {table.name} CASCADE"))
    await session.commit()


def make_app_with_session(session: AsyncSession):
    """Create a FastAPI app with get_db overridden to yield the given session."""
    app = create_app()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


def cleanup_app(app):
    app.dependency_overrides.clear()
