"""Общие структуры сервисного слоя."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection


def now_str() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def jloads(s: str | None, default: Any = None) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return default


def jdumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def log_change(conn: Connection, username: str, action: str, table_id: int | None = None,
               row_id: int | None = None, details: Any = None) -> None:
    conn.execute(text(
        "INSERT INTO wm_history(ts, username, table_id, row_id, action, details) "
        "VALUES (:ts, :u, :t, :r, :a, :d)"),
        {"ts": now_str(), "u": username, "t": table_id, "r": row_id, "a": action,
         "d": jdumps(details or {})})


def touch_table(conn: Connection, table_id: int) -> None:
    conn.execute(text("UPDATE wm_tables SET updated_at = :n WHERE id = :i"),
                 {"n": now_str(), "i": table_id})


@dataclass
class ColumnInfo:
    id: int
    name: str
    physical: str
    type: str
    position: int = 0
    required: bool = False
    default: str | None = None
    options: dict = field(default_factory=dict)
    width: int = 0
    indexed: bool = False


@dataclass
class TableInfo:
    id: int
    name: str
    kind: str
    physical: str
    category_id: int | None
    category: str
    archived: bool
    description: str
    created_at: dt.datetime
    updated_at: dt.datetime
    created_by: str
    columns: list[ColumnInfo]
    settings: dict = field(default_factory=dict)
    row_count: int | None = None

    def column(self, col_id: int) -> ColumnInfo:
        for c in self.columns:
            if c.id == col_id:
                return c
        raise KeyError(col_id)

    def column_by_name(self, name: str) -> ColumnInfo | None:
        low = name.strip().casefold()
        for c in self.columns:
            if c.name.casefold() == low:
                return c
        return None


@dataclass
class ColumnSpec:
    """Описание столбца для конструктора (id=None — новый столбец)."""
    name: str
    type: str = "text"
    required: bool = False
    default: str | None = None
    options: dict = field(default_factory=dict)
    indexed: bool = False
    width: int = 0
    id: int | None = None
