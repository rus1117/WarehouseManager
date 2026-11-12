"""Слой доступа к физическим таблицам пользовательских данных.

Весь SQL, зависящий от СУБД, сосредоточен здесь — для перехода на PostgreSQL
достаточно реализовать этот модуль заново, не трогая интерфейс и сервисы.

Защита от SQL-инъекций:
* значения всегда передаются как связанные параметры;
* имена таблиц/столбцов генерируются программой (data_<id>, c_<id>) и
  дополнительно проверяются регулярным выражением перед подстановкой.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Connection

_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
ROW_ID = "_id"
CREATED = "_created_at"
UPDATED = "_updated_at"
CHUNK = 500


def ident(name: str) -> str:
    if not _IDENT_RE.match(name):
        raise ValueError(f"Недопустимое имя объекта БД: {name!r}")
    return f'"{name}"'


def index_name(table: str, column: str) -> str:
    return f"ix_{table}_{column}"


@dataclass
class Condition:
    """Условие фильтра. op: contains, not_contains, equals, not_equals, starts, ends,
    empty, not_empty, gt, gte, lt, lte, between. value — уже в формате хранения
    (для текстовых операций — строка поиска)."""
    column: str          # физическое имя столбца или ROW_ID
    op: str
    value: Any = None
    value2: Any = None
    textual: bool = True  # текстовое сравнение без учёта регистра


TEXT_OPS = {"contains", "not_contains", "equals", "not_equals", "starts", "ends"}


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_where(conditions: Sequence[Condition], any_text: tuple[str, Sequence[str]] | None = None,
                match_all: bool = True) -> tuple[str, dict]:
    """Строит WHERE с параметрами. any_text=(строка, [столбцы]) — быстрый поиск по нескольким
    столбцам одновременно (OR)."""
    parts: list[str] = []
    params: dict[str, Any] = {}
    for i, c in enumerate(conditions):
        col = ident(c.column)
        p, p2 = f"p{i}", f"q{i}"
        op = c.op
        if op == "empty":
            parts.append(f"({col} IS NULL OR {col} = '')")
            continue
        if op == "not_empty":
            parts.append(f"({col} IS NOT NULL AND {col} <> '')")
            continue
        if c.textual and op in TEXT_OPS:
            from wm.db.engine import wm_lower
            needle = wm_lower(str(c.value)) or ""
            expr = f"wm_lower({col})"
            if op in ("contains", "not_contains"):
                params[p] = f"%{_like_escape(needle)}%"
                neg = "NOT " if op == "not_contains" else ""
                parts.append(f"(COALESCE({expr}, '') {neg}LIKE :{p} ESCAPE '\\')")
            elif op == "starts":
                params[p] = f"{_like_escape(needle)}%"
                parts.append(f"({expr} LIKE :{p} ESCAPE '\\')")
            elif op == "ends":
                params[p] = f"%{_like_escape(needle)}"
                parts.append(f"({expr} LIKE :{p} ESCAPE '\\')")
            elif op == "equals":
                params[p] = needle
                parts.append(f"({expr} = :{p})")
            else:
                params[p] = needle
                parts.append(f"(COALESCE({expr}, '') <> :{p})")
            continue
        sql_op = {"equals": "=", "not_equals": "<>", "gt": ">", "gte": ">=", "lt": "<",
                  "lte": "<="}.get(op)
        if sql_op:
            params[p] = c.value
            parts.append(f"({col} {sql_op} :{p})")
        elif op == "between":
            if c.value is not None:
                params[p] = c.value
                parts.append(f"({col} >= :{p})")
            if c.value2 is not None:
                params[p2] = c.value2
                parts.append(f"({col} <= :{p2})")
        else:
            raise ValueError(f"Неизвестная операция фильтра: {op}")
    joiner = " AND " if match_all else " OR "
    sql = joiner.join(parts)
    if any_text and any_text[0].strip() and any_text[1]:
        from wm.db.engine import wm_lower
        params["ft"] = f"%{_like_escape(wm_lower(any_text[0]) or '')}%"
        ors = " OR ".join(f"wm_lower({ident(c)}) LIKE :ft ESCAPE '\\'" for c in any_text[1])
        sql = f"({sql}) AND ({ors})" if sql else f"({ors})"
    return (f" WHERE {sql}" if sql else ""), params


class DataRepository:
    # ── структура ──────────────────────────────────────────────────
    @staticmethod
    def create_table(conn: Connection, table: str, columns: Iterable[tuple[str, str]]) -> None:
        cols = "".join(f", {ident(name)} {sql_type}" for name, sql_type in columns)
        conn.execute(text(
            f"CREATE TABLE {ident(table)} ({ident(ROW_ID)} INTEGER PRIMARY KEY AUTOINCREMENT, "
            f"{ident(CREATED)} TEXT, {ident(UPDATED)} TEXT{cols})"))

    @staticmethod
    def drop_table(conn: Connection, table: str) -> None:
        conn.execute(text(f"DROP TABLE IF EXISTS {ident(table)}"))

    @staticmethod
    def add_column(conn: Connection, table: str, column: str, sql_type: str) -> None:
        conn.execute(text(f"ALTER TABLE {ident(table)} ADD COLUMN {ident(column)} {sql_type}"))

    @classmethod
    def drop_column(cls, conn: Connection, table: str, column: str) -> None:
        cls.drop_index(conn, table, column)
        conn.execute(text(f"ALTER TABLE {ident(table)} DROP COLUMN {ident(column)}"))

    @staticmethod
    def create_index(conn: Connection, table: str, column: str) -> None:
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS {ident(index_name(table, column))} "
                          f"ON {ident(table)} ({ident(column)})"))

    @staticmethod
    def drop_index(conn: Connection, table: str, column: str) -> None:
        conn.execute(text(f"DROP INDEX IF EXISTS {ident(index_name(table, column))}"))

    @staticmethod
    def copy_data(conn: Connection, src: str, dst: str, src_cols: list[str],
                  dst_cols: list[str]) -> None:
        s = ", ".join(ident(c) for c in [CREATED, UPDATED, *src_cols])
        d = ", ".join(ident(c) for c in [CREATED, UPDATED, *dst_cols])
        conn.execute(text(f"INSERT INTO {ident(dst)} ({d}) SELECT {s} FROM {ident(src)} "
                          f"ORDER BY {ident(ROW_ID)}"))

    # ── данные ─────────────────────────────────────────────────────
    @staticmethod
    def insert(conn: Connection, table: str, columns: Sequence[str],
               rows: Sequence[Sequence[Any]], now: str) -> list[int]:
        """Вставляет строки, возвращает их идентификаторы."""
        if not rows:
            return []
        names = [CREATED, UPDATED, *columns]
        cols = ", ".join(ident(c) for c in names)
        placeholders = ", ".join(f":v{i}" for i in range(len(names)))
        sql = text(f"INSERT INTO {ident(table)} ({cols}) VALUES ({placeholders})")
        if len(rows) == 1:
            res = conn.execute(sql, {f"v{i}": v for i, v in enumerate([now, now, *rows[0]])})
            return [int(res.lastrowid)]
        max_before = conn.execute(text(
            f"SELECT COALESCE(MAX({ident(ROW_ID)}), 0) FROM {ident(table)}")).scalar()
        conn.execute(sql, [{f"v{i}": v for i, v in enumerate([now, now, *r])} for r in rows])
        return [int(x) for x in conn.execute(text(
            f"SELECT {ident(ROW_ID)} FROM {ident(table)} WHERE {ident(ROW_ID)} > :m "
            f"ORDER BY {ident(ROW_ID)}"), {"m": max_before}).scalars()]

    @staticmethod
    def insert_bulk(conn: Connection, table: str, columns: Sequence[str],
                    rows: Sequence[Sequence[Any]], now: str) -> None:
        """Быстрая массовая вставка без возврата идентификаторов (импорт)."""
        if not rows:
            return
        names = [CREATED, UPDATED, *columns]
        cols = ", ".join(ident(c) for c in names)
        q = ", ".join("?" for _ in names)
        conn.exec_driver_sql(f"INSERT INTO {ident(table)} ({cols}) VALUES ({q})",
                             [(now, now, *r) for r in rows])

    @staticmethod
    def update(conn: Connection, table: str, row_id: int, values: dict[str, Any],
               now: str) -> None:
        values = {**values, UPDATED: now}
        sets = ", ".join(f"{ident(k)} = :v{i}" for i, k in enumerate(values))
        params = {f"v{i}": v for i, v in enumerate(values.values())}
        params["rid"] = row_id
        conn.execute(text(f"UPDATE {ident(table)} SET {sets} WHERE {ident(ROW_ID)} = :rid"),
                     params)

    @staticmethod
    def fill_column(conn: Connection, table: str, column: str, value: Any) -> None:
        conn.execute(text(f"UPDATE {ident(table)} SET {ident(column)} = :v "
                          f"WHERE {ident(column)} IS NULL"), {"v": value})

    @staticmethod
    def delete(conn: Connection, table: str, ids: Sequence[int]) -> None:
        for i in range(0, len(ids), CHUNK):
            chunk = list(ids[i:i + CHUNK])
            ph = ", ".join(f":i{j}" for j in range(len(chunk)))
            conn.execute(text(f"DELETE FROM {ident(table)} WHERE {ident(ROW_ID)} IN ({ph})"),
                         {f"i{j}": v for j, v in enumerate(chunk)})

    @staticmethod
    def get_rows(conn: Connection, table: str, columns: Sequence[str],
                 ids: Sequence[int]) -> list[tuple]:
        out: list[tuple] = []
        cols = ", ".join(ident(c) for c in [ROW_ID, *columns])
        for i in range(0, len(ids), CHUNK):
            chunk = list(ids[i:i + CHUNK])
            ph = ", ".join(f":i{j}" for j in range(len(chunk)))
            out += [tuple(r) for r in conn.execute(text(
                f"SELECT {cols} FROM {ident(table)} WHERE {ident(ROW_ID)} IN ({ph}) "
                f"ORDER BY {ident(ROW_ID)}"), {f"i{j}": v for j, v in enumerate(chunk)})]
        return out

    @staticmethod
    def select(conn: Connection, table: str, columns: Sequence[str], where: str = "",
               params: dict | None = None, order_by: str | None = None, desc: bool = False,
               limit: int | None = None, offset: int = 0) -> list[tuple]:
        cols = ", ".join(ident(c) for c in [ROW_ID, *columns])
        order_col = ident(order_by or ROW_ID)
        direction = "DESC" if desc else "ASC"
        order = f" ORDER BY {order_col} {direction}"
        if order_by and order_by != ROW_ID:
            order += f", {ident(ROW_ID)} {direction}"
        sql = f"SELECT {cols} FROM {ident(table)}{where}{order}"
        p = dict(params or {})
        if limit is not None:
            sql += " LIMIT :_lim OFFSET :_off"
            p["_lim"], p["_off"] = int(limit), int(offset)
        return [tuple(r) for r in conn.execute(text(sql), p)]

    @staticmethod
    def iter_select(conn: Connection, table: str, columns: Sequence[str], where: str = "",
                    params: dict | None = None, order_by: str | None = None,
                    desc: bool = False, batch: int = 5000):
        """Потоковое чтение для экспорта больших таблиц."""
        cols = ", ".join(ident(c) for c in [ROW_ID, *columns])
        order = f" ORDER BY {ident(order_by or ROW_ID)} {'DESC' if desc else 'ASC'}"
        result = conn.execution_options(stream_results=True).execute(
            text(f"SELECT {cols} FROM {ident(table)}{where}{order}"), params or {})
        while True:
            rows = result.fetchmany(batch)
            if not rows:
                break
            yield [tuple(r) for r in rows]

    @staticmethod
    def count(conn: Connection, table: str, where: str = "", params: dict | None = None) -> int:
        return int(conn.execute(text(f"SELECT COUNT(*) FROM {ident(table)}{where}"),
                                params or {}).scalar() or 0)

    @staticmethod
    def column_values(conn: Connection, table: str, column: str) -> list[Any]:
        return list(conn.execute(text(
            f"SELECT {ident(ROW_ID)}, {ident(column)} FROM {ident(table)} "
            f"WHERE {ident(column)} IS NOT NULL")))

    @staticmethod
    def distinct_values(conn: Connection, table: str, column: str, limit: int = 3000) -> list[str]:
        rows = conn.execute(text(
            f"SELECT {ident(column)} FROM {ident(table)} WHERE {ident(column)} IS NOT NULL "
            f"AND {ident(column)} <> '' GROUP BY {ident(column)} "
            f"ORDER BY MAX({ident(ROW_ID)}) DESC LIMIT :lim"), {"lim": limit})
        return [str(r[0]) for r in rows]

    @staticmethod
    def exists_exact(conn: Connection, table: str, columns: Sequence[str],
                     values: Sequence[Any]) -> bool:
        conds, params = [], {}
        for i, (c, v) in enumerate(zip(columns, values)):
            if v is None:
                conds.append(f"{ident(c)} IS NULL")
            else:
                conds.append(f"{ident(c)} = :v{i}")
                params[f"v{i}"] = v
        where = " AND ".join(conds) or "1=1"
        return conn.execute(text(f"SELECT 1 FROM {ident(table)} WHERE {where} LIMIT 1"),
                            params).first() is not None

    @staticmethod
    def all_hashes(conn: Connection, table: str, columns: Sequence[str]) -> set[tuple]:
        if not columns:
            return set()
        cols = ", ".join(ident(c) for c in columns)
        return {tuple(r) for r in conn.execute(text(f"SELECT {cols} FROM {ident(table)}"))}

    @staticmethod
    def last_modified(conn: Connection, table: str) -> str | None:
        return conn.execute(text(f"SELECT MAX({ident(UPDATED)}) FROM {ident(table)}")).scalar()
