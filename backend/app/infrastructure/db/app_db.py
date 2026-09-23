from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.settings import Settings

engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def init_db(settings: Settings) -> None:
    global engine, SessionLocal
    if engine is not None:
        engine.dispose()
    database_path = settings.data_dir / "app.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        "sqlite:///" + database_path.resolve().as_posix(),
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)


@contextmanager
def db_session() -> Iterator[Session]:
    if SessionLocal is None:
        raise RuntimeError("database is not initialized")
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    if SessionLocal is None:
        raise RuntimeError("database is not initialized")
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
