"""SQLAlchemy async engine and session factory.

Targets SQLite via aiosqlite.  The schema uses Oracle-style naming
conventions (UPPERCASE table/column names) so it maps 1-to-1 onto an
Oracle DB in production — swap the DATABASE_URL in .env to connect.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    # SQLite-specific: allow connections across threads (needed by aiosqlite)
    connect_args={"check_same_thread": False},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields a session and commits/rolls back on exit."""
    async with async_session() as session:
        yield session


async def init_db() -> None:
    """Create all tables declared in models.py (idempotent)."""
    from backend.db.models import Base  # local import avoids circular deps

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
