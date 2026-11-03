"""Database engine and transaction lifecycle helpers."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


class Database:
    """Own the application SQLAlchemy engine and request-session factory."""

    def __init__(self, database_url: str) -> None:
        self.engine: Engine = create_engine(database_url, pool_pre_ping=True)
        self._session_factory = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

    def session(self) -> Generator[Session, None, None]:
        """Yield one request-scoped session and roll back incomplete work."""

        database_session = self._session_factory()
        try:
            yield database_session
        except Exception:
            database_session.rollback()
            raise
        finally:
            database_session.close()
