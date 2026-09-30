import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.db.schema import ensure_schema
from app.settings import Settings

logger = logging.getLogger(__name__)

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
        cursor.execute("PRAGMA busy_timeout=5000")
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
        except Exception as exc:
            # 数据库目录不可写时退回默认日志模式，不让启动整体失败。
            logger.warning("无法启用 WAL 日志模式，改用默认模式：%s", exc)
        finally:
            cursor.close()

    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    for note in ensure_schema(engine):
        logger.warning("数据库结构已调整：%s", note)


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
    with db_session() as session:
        yield session
