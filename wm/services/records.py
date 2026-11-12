"""Работа с записями: чтение постранично, добавление, редактирование, удаление."""
from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any, Sequence

from sqlalchemy import text

from wm.core import types as T
from wm.core.errors import NotFound, ValidationError
from wm.core.security import P_DATA_PURGE, P_DATA_READ, P_DATA_WRITE
from wm.db.repository import DataRepository as Repo, ROW_ID, Condition, build_where
from wm.services.common import ColumnInfo, TableInfo, log_change, now_str, touch_table

if TYPE_CHECKING:
    from wm.app_context import AppContext

MAX_BATCH = 100_000


def resolve_default(col: ColumnInfo) -> Any:
    d = col.default
    if d in (None, ""):
        return None
    now = dt.datetime.now().replace(microsecond=0)
    if d == "{today}":
        return T.to_storage(col.type, now.date() if col.type == T.DATE else now)
    if d == "{now}":
        return T.to_storage(col.type, now)
    if d == "{time}":
        return T.to_storage(col.type, now.time())
    try:
        return T.to_storage(col.type, d, col.options)
    except ValueError:
        return None


def default_display(col: ColumnInfo) -> str:
    v = resolve_default(col)
    return T.to_edit_text(col.type, v) if v is not None else ""


class RecordService:
    def __init__(self, ctx: "AppContext") -> None:
        self.ctx = ctx

    @property
    def db(self):
        return self.ctx.db

    def _table(self, table_id: int) -> TableInfo:
        return self.ctx.tables.get(table_id)

    # ── проверка ───────────────────────────────────────────────────
    @staticmethod
    def convert(col: ColumnInfo, raw: Any) -> Any:
        try:
            value = T.to_storage(col.type, raw, col.options)
        except ValueError as exc:
            raise ValidationError(f"«{col.name}»: {exc}") from None
        if value is None and col.required:
            raise ValidationError(f"Поле «{col.name}» обязательно для заполнения.")
        return value

    def prepare(self, table: TableInfo, raw: dict[int, Any], apply_defaults: bool = True) -> list:
        """Готовит полную строку для вставки (в порядке столбцов таблицы)."""
        values, errors = [], []
        for col in table.columns:
            v = raw.get(col.id)
            try:
                if T.is_empty(v) and apply_defaults:
                    val = resolve_default(col)
                    if val is None and col.required:
                        raise ValidationError(f"Поле «{col.name}» обязательно для заполнения.")
                else:
                    val = self.convert(col, v)
                values.append(val)
            except ValidationError as exc:
                errors.append(str(exc))
        if errors:
            raise ValidationError("\n".join(errors))
        return values

    # ── чтение ─────────────────────────────────────────────────────
    def fetch(self, table: TableInfo, conditions: Sequence[Condition] = (), quick: str = "",
              sort_col: int | None = None, desc: bool = False, limit: int = 500,
              offset: int = 0, match_all: bool = True) -> list[tuple]:
        self.ctx.session.require(P_DATA_READ)
        where, params = self._where(table, conditions, quick, match_all)
        order = table.column(sort_col).physical if sort_col else ROW_ID
        with self.db.connect() as conn:
            return Repo.select(conn, table.physical, [c.physical for c in table.columns], where,
                               params, order, desc, limit, offset)

    def count(self, table: TableInfo, conditions: Sequence[Condition] = (), quick: str = "",
              match_all: bool = True) -> int:
        self.ctx.session.require(P_DATA_READ)
        where, params = self._where(table, conditions, quick, match_all)
        with self.db.connect() as conn:
            return Repo.count(conn, table.physical, where, params)

    @staticmethod
    def _where(table: TableInfo, conditions, quick: str, match_all: bool = True):
        quick_cols = [c.physical for c in table.columns] if quick and quick.strip() else []
        return build_where(list(conditions), (quick, quick_cols) if quick_cols else None, match_all)

    def get(self, table: TableInfo, ids: Sequence[int]) -> list[tuple]:
        self.ctx.session.require(P_DATA_READ)
        with self.db.connect() as conn:
            return Repo.get_rows(conn, table.physical, [c.physical for c in table.columns], ids)

    def distinct(self, table: TableInfo, col_id: int, limit: int = 3000) -> list[str]:
        self.ctx.session.require(P_DATA_READ)
        with self.db.connect() as conn:
            return Repo.distinct_values(conn, table.physical, table.column(col_id).physical, limit)

    # ── изменение ──────────────────────────────────────────────────
    def insert(self, table_id: int, raw: dict[int, Any]) -> int:
        return self.insert_many(table_id, [raw])[0]

    def insert_many(self, table_id: int, raws: Sequence[dict[int, Any]],
                    apply_defaults: bool = True) -> list[int]:
        """Добавляет строки атомарно: либо все, либо ни одной."""
        self.ctx.session.require(P_DATA_WRITE)
        if len(raws) > MAX_BATCH:
            raise ValidationError(f"За один раз можно добавить не более {MAX_BATCH} строк.")
        table = self._table(table_id)
        rows, errors = [], []
        for i, raw in enumerate(raws, 1):
            try:
                rows.append(self.prepare(table, raw, apply_defaults))
            except ValidationError as exc:
                errors.append(f"Строка {i}: {exc}" if len(raws) > 1 else str(exc))
        if errors:
            raise ValidationError("\n".join(errors[:20]) +
                                  (f"\n… и ещё {len(errors) - 20}" if len(errors) > 20 else ""))
        with self.db.begin() as conn:
            ids = Repo.insert(conn, table.physical, [c.physical for c in table.columns], rows,
                              now_str())
            touch_table(conn, table_id)
            if len(ids) == 1:
                log_change(conn, self.ctx.session.username, "row_insert", table_id, ids[0])
            else:
                log_change(conn, self.ctx.session.username, "rows_insert", table_id,
                           details={"count": len(ids)})
        return ids

    def update_cell(self, table_id: int, row_id: int, col_id: int, raw: Any) -> Any:
        return self.update(table_id, row_id, {col_id: raw})[col_id]

    def update(self, table_id: int, row_id: int, raw: dict[int, Any]) -> dict[int, Any]:
        self.ctx.session.require(P_DATA_WRITE)
        table = self._table(table_id)
        new_values: dict[int, Any] = {}
        errors = []
        for cid, v in raw.items():
            try:
                new_values[cid] = self.convert(table.column(cid), v)
            except ValidationError as exc:
                errors.append(str(exc))
        if errors:
            raise ValidationError("\n".join(errors))
        with self.db.begin() as conn:
            cols = [table.column(cid) for cid in new_values]
            old = Repo.get_rows(conn, table.physical, [c.physical for c in cols], [row_id])
            if not old:
                raise NotFound("Запись не найдена (возможно, удалена).")
            changed = {c.physical: new_values[c.id] for c, o in zip(cols, old[0][1:])
                       if o != new_values[c.id]}
            if changed:
                Repo.update(conn, table.physical, row_id, changed, now_str())
                touch_table(conn, table_id)
                log_change(conn, self.ctx.session.username, "row_update", table_id, row_id, {
                    c.name: {"old": o, "new": new_values[c.id]}
                    for c, o in zip(cols, old[0][1:]) if o != new_values[c.id]})
        return new_values

    def delete(self, table_id: int, ids: Sequence[int], purge_history: bool = False) -> int:
        """Удаляет записи. purge_history=True — окончательное удаление вместе с историей
        (по запросу субъекта персональных данных, только администратор)."""
        self.ctx.session.require(P_DATA_PURGE if purge_history else P_DATA_WRITE)
        ids = sorted({int(i) for i in ids})
        if not ids:
            return 0
        table = self._table(table_id)
        with self.db.begin() as conn:
            if purge_history:
                for i in range(0, len(ids), 500):
                    chunk = ids[i:i + 500]
                    ph = ", ".join(f":i{j}" for j in range(len(chunk)))
                    conn.execute(text(
                        f"DELETE FROM wm_history WHERE table_id = :t AND row_id IN ({ph})"),
                        {"t": table_id, **{f"i{j}": v for j, v in enumerate(chunk)}})
                log_change(conn, self.ctx.session.username, "rows_purge", table_id,
                           details={"count": len(ids)})
            else:
                old = Repo.get_rows(conn, table.physical, [c.physical for c in table.columns], ids)
                if len(old) <= 1000:
                    for r in old:
                        log_change(conn, self.ctx.session.username, "row_delete", table_id, r[0],
                                   {c.name: v for c, v in zip(table.columns, r[1:])})
                else:
                    log_change(conn, self.ctx.session.username, "rows_delete", table_id,
                               details={"count": len(old)})
            Repo.delete(conn, table.physical, ids)
            touch_table(conn, table_id)
        return len(ids)

    def duplicate(self, table_id: int, ids: Sequence[int]) -> list[int]:
        self.ctx.session.require(P_DATA_WRITE)
        table = self._table(table_id)
        with self.db.begin() as conn:
            rows = Repo.get_rows(conn, table.physical, [c.physical for c in table.columns], ids)
            new_ids = Repo.insert(conn, table.physical, [c.physical for c in table.columns],
                                  [r[1:] for r in rows], now_str())
            touch_table(conn, table_id)
            log_change(conn, self.ctx.session.username, "rows_copy", table_id,
                       details={"count": len(new_ids)})
        return new_ids
