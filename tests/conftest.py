import os
import tempfile
from typing import AsyncGenerator

import pytest

# Set a temp DB URL for all tests BEFORE any models or session are imported
fd, temp_db = tempfile.mkstemp(suffix=".db")
os.close(fd)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{temp_db}"

from app.db.session import Base, engine


@pytest.fixture(autouse=True)
async def setup_test_db() -> AsyncGenerator[None, None]:
    """Create all tables before each test and drop them after."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()
    try:
        os.remove(temp_db)
    except Exception:
        pass
