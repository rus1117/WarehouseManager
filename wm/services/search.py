"""Поиск и фильтрация: условия по столбцам, диапазоны, глобальный поиск, сохранённые фильтры."""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from wm.core import types as T
from wm.core.errors import ValidationError
from wm.core.security import P_DATA_READ
from wm.db.models import SavedFilter
from wm.db.repository import Condition, DataRepository as Repo, build_where
from wm.services.common import ColumnInfo, TableInfo, jdumps, jloads

if TYPE_CHECKING:
    from wm.app_context import AppContext

OPS = {
    "contains": "содержит",
    "equals": "равно",
    "starts": "начинается с",
    "ends": "заканчивается на",
    "not_contains": "не содержит",
    "not_equals": "не равно",
    "between": "в диапазоне",
    "gte": "не меньше (≥)",
    "lte": "не больше (≤)",
    "gt": "больше (>)",
    "lt": "меньше (<)",
    "empty": "пусто",
    "not_empty": "заполнено",
}


def ops_for_type(type_code: str) -> list[str]:
    if type_code in T.TEXTUAL:
        return ["contains", "equals", "starts", "ends", "not_contains", "not_equals",
                "empty", "not_empty"]
    if type_code == T.BOOL:
        return ["equals", "empty", "not_empty"]
    return ["equals", "between", "gte", "lte", "gt", "lt", "not_equals", "empty", "not_empty"]


@dataclass
class FilterSpec:
    """Условие в терминах пользователя (сырые значения)."""
    column_id: int
    op: str
    value: Any = ""
    value2: Any = ""


def to_condition(col: ColumnInfo, spec: FilterSpec) -> list[Condition]:
    op = spec.op
    if op not in OPS:
        raise ValidationError(f"Неизвестная операция: {op}")
    if op in ("empty", "not_empty"):
        return [Condition(col.physical, op)]
    if col.type in T.TEXTUAL:
        if T.is_empty(spec.value):
            return []
        return [Condition(col.physical, op, str(spec.value), textual=True)]

    def conv(v, end: bool = False):
        if T.is_empty(v):
            return None
        try:
            if col.type == T.DATETIME:
                s = str(v).strip()
                try:
                    d = T.to_storage(T.DATE, s) if ":" not in s else None
                except ValueError:
                    d = None
                if d is not None:  # только дата — граница суток
                    return f"{d} 23:59:59" if end else f"{d} 00:00:00"
            return T.to_storage(col.type, v, col.options)
        except ValueError as exc:
            raise ValidationError(f"«{col.name}»: {exc}") from None

    if op == "between":
        a, b = conv(spec.value), conv(spec.value2, end=True)
        if a is None and b is None:
            return []
        return [Condition(col.physical, "between", a, b, textual=False)]
    value = conv(spec.value)
    if value is None:
        return []
    if col.type == T.DATETIME and op == "equals" and ":" not in str(spec.value):
        return [Condition(col.physical, "between", value, conv(spec.value, end=True),
                          textual=False)]
    return [Condition(col.physical, op, value, textual=False)]


class SearchService:
    def __init__(self, ctx: "AppContext") -> None:
        self.ctx = ctx

    def build(self, table: TableInfo, specs: list[FilterSpec]) -> list[Condition]:
        conds: list[Condition] = []
        for s in specs:
            try:
                col = table.column(s.column_id)
            except KeyError:
                continue  # столбец удалён — условие игнорируем
            conds += to_condition(col, s)
        return conds

    def global_search(self, query: str, limit_per_table: int = 50,
                      include_archived: bool = False) -> list[tuple[TableInfo, int, list[tuple]]]:
        """Ищет строку во всех столбцах всех таблиц. Возвращает [(таблица, всего, строки)]."""
        self.ctx.session.require(P_DATA_READ)
        query = T.normalize_spaces(query or "")
        if not query:
            return []
        needles = [query]
        for code in (T.DATE, T.DATETIME):
            try:
                needles.append(T.to_storage(code, query))
                break
            except ValueError:
                pass
        try:
            num = T.to_storage(T.FLOAT, query)
            needles.append(f"{num:g}")
        except ValueError:
            pass
        results = []
        for table in self.ctx.tables.list(include_archived=include_archived, with_counts=False):
            conds = [Condition(c.physical, "contains", n, textual=True)
                     for c in table.columns for n in dict.fromkeys(needles)]
            if not conds:
                continue
            where, params = build_where(conds, match_all=False)
            with self.ctx.db.connect() as conn:
                total = Repo.count(conn, table.physical, where, params)
                if total:
                    rows = Repo.select(conn, table.physical, [c.physical for c in table.columns],
                                       where, params, None, True, limit_per_table, 0)
                    results.append((table, total, rows))
        return results

    # ── сохранённые фильтры ────────────────────────────────────────
    def save_filter(self, table_id: int, name: str, specs: list[FilterSpec], quick: str = "",
                    match_all: bool = True) -> int:
        self.ctx.session.require(P_DATA_READ)
        name = T.normalize_spaces(name or "")
        if not name:
            raise ValidationError("Укажите название фильтра.")
        definition = jdumps({"conditions": [asdict(s) for s in specs], "quick": quick,
                             "match_all": match_all})
        with self.ctx.db.session() as s:
            existing = s.scalar(select(SavedFilter).where(
                SavedFilter.table_id == table_id, SavedFilter.name == name))
            if existing:
                existing.definition = definition
                return existing.id
            f = SavedFilter(table_id=table_id, name=name, definition=definition,
                            created_by=self.ctx.session.username)
            s.add(f)
            s.flush()
            return f.id

    def saved_filters(self, table_id: int) -> list[tuple[int, str, list[FilterSpec], str, bool]]:
        self.ctx.session.require(P_DATA_READ)
        with self.ctx.db.session() as s:
            out = []
            for f in s.scalars(select(SavedFilter).where(SavedFilter.table_id == table_id)
                               .order_by(SavedFilter.name)):
                d = jloads(f.definition, {}) or {}
                specs = [FilterSpec(**c) for c in d.get("conditions", [])]
                out.append((f.id, f.name, specs, d.get("quick", ""), d.get("match_all", True)))
            return out

    def delete_filter(self, filter_id: int) -> None:
        self.ctx.session.require(P_DATA_READ)
        with self.ctx.db.session() as s:
            f = s.get(SavedFilter, filter_id)
            if f:
                s.delete(f)


_ = dt
