"""
Database engine & session factory.

SQLite by default (backend/scheduler.db). Set DATABASE_URL to use PostgreSQL, e.g.
    export DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/econ_scheduler
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(BACKEND_DIR, 'scheduler.db')}")
# Many hosts (RDS secrets, Heroku, Render) hand out postgres:// URLs; SQLAlchemy needs the dialect name.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgresql://"):]

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True, pool_pre_ping=True)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_fk(dbapi_conn, _record):
        # Enforce ON DELETE CASCADE / SET NULL like PostgreSQL does
        dbapi_conn.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Additive columns introduced after the first deploy: create_all() only creates missing
# tables, so existing databases (e.g. a hosted Postgres) get these via ALTER TABLE.
_ADDED_COLUMNS = {
    "faculty": {"fall_courseload": "INTEGER", "spring_courseload": "INTEGER"},
    "preference_submissions": {"submitted_by": "VARCHAR(200)"},
    "schedule_overrides": {"cap": "INTEGER"},
}
# Renamed faculty-group labels stored in older databases
_RENAMED_FACULTY_TYPES = {"Tenured": "Tenured Track / Tenured"}


def _migrate():
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in _ADDED_COLUMNS.items():
            if not insp.has_table(table):
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for name, sql_type in cols.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
        if insp.has_table("faculty"):
            for old, new in _RENAMED_FACULTY_TYPES.items():
                conn.execute(text("UPDATE faculty SET faculty_type = :new WHERE faculty_type = :old"),
                             {"new": new, "old": old})


def init_db():
    from models import Base as _Base  # noqa: F401 — registers all models

    Base.metadata.create_all(bind=engine)
    _migrate()
