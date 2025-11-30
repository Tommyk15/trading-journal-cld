"""Pytest configuration and fixtures."""

import asyncio
from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from trading_journal.core.database import Base, get_db
from trading_journal.main import app

# Test database URL (use SQLite for testing)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
)

# Create test session factory
TestSessionLocal = sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="function")
def client(db_session: AsyncSession) -> Generator:
    """Create a test client with database session."""

    async def override_get_db():
        yield db_session

    # Override the lifespan to skip database initialization
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def test_lifespan(app):
        # Skip database initialization in tests
        yield

    # Replace the app lifespan
    from trading_journal.main import app as main_app

    original_lifespan = main_app.router.lifespan_context
    main_app.router.lifespan_context = test_lifespan

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    # Restore original lifespan
    main_app.router.lifespan_context = original_lifespan
    app.dependency_overrides.clear()
