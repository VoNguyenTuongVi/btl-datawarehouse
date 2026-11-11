"""Database connection configuration shared by the ETL and quality checks."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine

from env_config import get_database_url

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_URL = f"sqlite:///{PROJECT_ROOT / 'car_sales_dw.db'}"


def create_database_engine() -> Engine:
    """Create an engine from DATABASE_URL (.env first), defaulting to the local SQLite DW."""
    database_url = get_database_url(DEFAULT_DATABASE_URL)
    if not database_url.startswith(("sqlite:///", "postgresql://", "postgresql+psycopg2://")):
        raise ValueError("DATABASE_URL must use SQLite or PostgreSQL.")
    return create_engine(database_url, pool_pre_ping=database_url.startswith("postgresql"))
