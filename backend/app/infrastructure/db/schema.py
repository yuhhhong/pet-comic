"""启动时把 SQLite 表结构对齐到当前代码模型。

只比较列名。SQLite 是动态类型，历史手写 SQL 建出的 TEXT 和模型的 VARCHAR 等价，
所以类型差异不算结构问题。真正会打断启动的是缺列、多列，以及旧表上的 NOT NULL 约束。
"""

import logging
from typing import Any

from sqlalchemy import Column, MetaData, Table, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateColumn, CreateIndex, DropTable

from app.infrastructure.db import models  # noqa: F401  导入模型以注册表元数据
from app.infrastructure.db.base import Base

logger = logging.getLogger(__name__)


def ensure_schema(engine: Engine) -> list[str]:
    """创建缺失的表，并把结构过期的表对齐到当前模型，返回本次调整的说明。"""
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    adjustments: list[str] = []
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        expected = {column.name for column in table.columns}
        if actual != expected:
            adjustments.append(_realign(engine, table, actual, expected))
    return adjustments


def _realign(engine: Engine, table: Table, actual: set[str], expected: set[str]) -> str:
    missing = sorted(expected - actual)
    if not actual - expected and all(_can_add_column(table.c[name]) for name in missing):
        # 新增可空的普通列可直接 ALTER，保留原表、索引和外键关系。
        with engine.begin() as connection:
            table_name = engine.dialect.identifier_preparer.format_table(table)
            for name in missing:
                definition = CreateColumn(table.c[name]).compile(dialect=engine.dialect)
                connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {definition}")
        return f"{table.name}：补齐 {', '.join(missing)}"
    rows = _count(engine, table.name)
    shared = sorted(expected & actual)
    _rebuild(engine, table, shared)
    extra = sorted(actual - expected)
    note = f"{table.name}："
    note += f"已重建并保留 {rows} 行" if rows else "旧表为空，已按当前模型重建"
    if missing:
        note += f"，补齐 {', '.join(missing)}"
    if extra:
        note += f"，移除 {', '.join(extra)}"
    return note


def _can_add_column(column: Column[Any]) -> bool:
    return (
        column.nullable and not column.primary_key and not column.unique and not column.index and not column.foreign_keys
        and column.server_default is None and column.computed is None and column.identity is None
    )


def _count(engine: Engine, table_name: str) -> int:
    with engine.connect() as connection:
        rows = int(connection.scalar(text(f'SELECT COUNT(*) FROM "{table_name}"')) or 0)
        connection.rollback()
    return rows


def _rebuild(engine: Engine, table: Table, shared: list[str]) -> None:
    """按当前模型重建一张表。外键检查必须关闭，否则重建父表会被子表挡住。"""
    temporary = f"{table.name}__migrate"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        # PRAGMA 在事务内会被忽略，所以这里显式控制事务边界。
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql("PRAGMA legacy_alter_table=ON")
        connection.exec_driver_sql("BEGIN")
        try:
            connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{temporary}"')
            clone = table.to_metadata(MetaData(), name=temporary)
            clone.create(connection)
            if shared:
                columns = ", ".join(f'"{name}"' for name in shared)
                connection.exec_driver_sql(
                    f'INSERT INTO "{temporary}" ({columns}) SELECT {columns} FROM "{table.name}"'
                )
            connection.execute(DropTable(table))
            connection.exec_driver_sql(f'ALTER TABLE "{temporary}" RENAME TO "{table.name}"')
            _recreate_indexes(connection, table)
            connection.exec_driver_sql("COMMIT")
        except Exception:
            connection.exec_driver_sql("ROLLBACK")
            raise
        finally:
            # 连接会回到连接池，必须把这两个开关恢复原状。
            connection.exec_driver_sql("PRAGMA legacy_alter_table=OFF")
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def _recreate_indexes(connection, table: Table) -> None:
    # 索引建在临时表名下，改名后名字不会跟着变，所以先删掉再按正式名字重建。
    existing = [row[1] for row in connection.exec_driver_sql(f'PRAGMA index_list("{table.name}")').all() if row[3] == "c"]
    for name in existing:
        connection.exec_driver_sql(f'DROP INDEX IF EXISTS "{name}"')
    for index in table.indexes:
        connection.execute(CreateIndex(index))
