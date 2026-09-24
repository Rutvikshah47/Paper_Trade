from pathlib import Path
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

DB_PATH = Path(
    os.environ.get(
        "PAPER_TRADER_DB_PATH",
        str(Path(__file__).resolve().parents[1] / "paper_trader.db"),
    )
)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    poolclass=NullPool,
    connect_args={
        "check_same_thread": False,
        # Give concurrent requests time to wait for SQLite's single writer.
        "timeout": 30,
    },
)

@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
