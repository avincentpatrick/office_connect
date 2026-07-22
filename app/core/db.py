"""Async SQLAlchemy engine + session factory.

Pool sized per plan §17.1 (size 10 / overflow 20). This is the single DB
choke-point CSS-IS's storage.py is migrated onto in Phase 1.
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
