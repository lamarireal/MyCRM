import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest_asyncio.fixture
async def database_session() -> AsyncIterator[AsyncSession]:
    database_url = os.getenv("MYCRM_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("MYCRM_TEST_DATABASE_URL is required for PostgreSQL integration tests")

    engine = create_async_engine(database_url, pool_pre_ping=True)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()
