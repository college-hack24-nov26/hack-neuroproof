"""SQLAlchemy declarative base shared by all persistence entities."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Root metadata class used by Alembic migrations."""
