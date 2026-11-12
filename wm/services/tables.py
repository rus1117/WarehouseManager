"""Управление таблицами: создание, структура, копирование, архив, категории."""
from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import func, select, text

from wm.core import types as T
from wm.core.errors import NotFound, ValidationError
from wm.core.security import (
    P_DATA_READ, P_TABLE_ARCHIVE, P_TABLE_CREATE, P_TABLE_DELETE, P_TABLE_STRUCTURE,
)
from wm.db.models import Category, TableColumn, UserTable, utcnow
from wm.db.repository import DataRepository as Repo
from wm.services.common import (
    ColumnInfo, ColumnSpec, TableInfo, jdumps, jloads, log_change, now_str,
)

if TYPE_CHECKING:
    from wm.app_context import AppContext

MAX_NAME = 200
MAX_COLUMNS = 500
SPECIAL_DEFAULTS = {"{today}", "{now}", "{time}"}


def _to_info(t: UserTable) -> TableInfo:
    return TableInfo(
        id=t.id, name=t.name, kind=t.kind, physical=t.physical_name,
        category_id=t.category_id, category=t.category.name if t.category else "",
        archived=t.is_archived, description=t.description or "",
        created_at=t.created_at, updated_at=t.updated_at, created_by=t.created_by or "",
        settings=jloads(t.settings, {}) or {},
        columns=[ColumnInfo(
            id=c.id, name=c.name, physical=c.physical_name, type=c.type, position=c.position,
            required=c.required, default=c.default_value, options=jloads(c.options, {}) or {},
            width=c.width or 0, indexed=c.indexed) for c in sorted(t.columns, key=lambda x: x.position)],
    )


def validate_default(spec: ColumnSpec) -> None:
    if spec.default in (None, ""):
        spec.default = None
        return
    if spec.default in SPECIAL_DEFAULTS:
        allowed = {"{today}": {T.DATE, T.DATETIME}, "{now}": {T.DATETIME, T.DATE, T.TIME},
                   "{time}": {T.TIME}}[spec.default]
        if spec.type not in allowed:
            raise ValidationError(f"Столбец «{spec.name}»: автозначение не подходит к типу.")
        return
    try:
        T.to_storage(spec.type, spec.default, spec.options)
    except ValueError as exc:
        raise ValidationError(f"Столбец «{spec.name}»: значение по умолчанию — {exc}") from None


def validate_specs(specs: list[ColumnSpec]) -> None:
    if not specs:
        raise ValidationError("Таблица должна содержать хотя бы один столбец.")
    if len(specs) > MAX_COLUMNS:
        raise ValidationError(f"Слишком много столбцов (максимум {MAX_COLUMNS}).")
    seen: set[str] = set()
    for s in specs:
        s.name = T.normalize_spaces(s.name or "")
        if not s.name:
            raise ValidationError("У каждого столбца должно быть название.")
        if len(s.name) > MAX_NAME:
            raise ValidationError(f"Название столбца «{s.name[:30]}…» слишком длинное.")
        key = s.name.casefold()
        if key in seen:
            raise ValidationError(f"Столбец «{s.name}» указан дважды.")
        seen.add(key)
        if s.type not in T.TYPES:
            raise ValidationError(f"Неизвестный тип данных столбца «{s.name}».")
        if s.type == T.CHOICE:
            choices = [T.normalize_spaces(str(c)) for c in s.options.get("choices", []) if str(c).strip()]
            s.options["choices"] = list(dict.fromkeys(choices))
        validate_default(s)


class TableService:
    def __init__(self, ctx: "AppContext") -> None:
        self.ctx = ctx

    @property
    def db(self):
        return self.ctx.db

    # ── чтение ─────────────────────────────────────────────────────
    def get(self, table_id: int, with_count: bool = False) -> TableInfo:
        self.ctx.session.require(P_DATA_READ)
        with self.db.session() as s:
            t = s.get(UserTable, table_id)
            if t is None:
                raise NotFound("Таблица не найдена (возможно, удалена).")
            info = _to_info(t)
        if with_count:
            with self.db.connect() as conn:
                info.row_count = Repo.count(conn, info.physical)
        return info

    def list(self, include_archived: bool = False, archived_only: bool = False,
             with_counts: bool = True) -> list[TableInfo]:
        self.ctx.session.require(P_DATA_READ)
        with self.db.session() as s:
            q = select(UserTable)
            if archived_only:
                q = q.where(UserTable.is_archived.is_(True))
            elif not include_archived:
                q = q.where(UserTable.is_archived.is_(False))
            tables = [_to_info(t) for t in s.scalars(q.order_by(UserTable.name))]
        if with_counts:
            with self.db.connect() as conn:
                for t in tables:
                    t.row_count = Repo.count(conn, t.physical)
        return tables

    def name_exists(self, name: str, exclude_id: int | None = None) -> bool:
        low = T.normalize_spaces(name).casefold()
        with self.db.session() as s:
            for tid, tname in s.execute(select(UserTable.id, UserTable.name)):
                if tid != exclude_id and tname.casefold() == low:
                    return True
        return False

    def _check_name(self, name: str, exclude_id: int | None = None) -> str:
        name = T.normalize_spaces(name or "")
        if not name:
            raise ValidationError("Укажите название таблицы.")
        if len(name) > MAX_NAME:
            raise ValidationError("Название таблицы слишком длинное (максимум 200 символов).")
        if self.name_exists(name, exclude_id):
            raise ValidationError(f"Таблица «{name}» уже существует. Выберите другое название.")
        return name

    def unique_name(self, base: str) -> str:
        base = T.normalize_spaces(base) or "Таблица"
        name, n = base, 2
        while self.name_exists(name):
            name = f"{base} ({n})"
            n += 1
        return name

    # ── создание ───────────────────────────────────────────────────
    def create(self, name: str, specs: list[ColumnSpec], kind: str = "generic",
               category_id: int | None = None, description: str = "", conn_session=None) -> int:
        self.ctx.session.require(P_TABLE_CREATE)
        name = self._check_name(name)
        validate_specs(specs)
        with self.db.session() as s:
            table_id = self._create_in_session(s, name, specs, kind, category_id, description)
        return table_id

    def _create_in_session(self, s, name, specs, kind, category_id, description) -> int:
        t = UserTable(name=name, kind=kind, category_id=category_id, description=description,
                      created_by=self.ctx.session.username, physical_name=f"tmp_{id(specs)}")
        s.add(t)
        s.flush()
        t.physical_name = f"data_{t.id}"
        cols = []
        for pos, spec in enumerate(specs):
            c = TableColumn(table_id=t.id, name=spec.name, type=spec.type, position=pos,
                            required=spec.required, default_value=spec.default,
                            options=jdumps(spec.options or {}), width=spec.width or 0,
                            indexed=spec.indexed, physical_name=f"tmp_{pos}")
            s.add(c)
            cols.append(c)
        s.flush()
        for c in cols:
            c.physical_name = f"c_{c.id}"
        s.flush()
        conn = s.connection()
        Repo.create_table(conn, t.physical_name, [(c.physical_name, T.TYPES[c.type].sql) for c in cols])
        for c in cols:
            if c.indexed:
                Repo.create_index(conn, t.physical_name, c.physical_name)
        log_change(conn, self.ctx.session.username, "table_create", t.id,
                   details={"name": name, "columns": [c.name for c in cols]})
        return t.id

    # ── структура ──────────────────────────────────────────────────
    def update_structure(self, table_id: int, specs: list[ColumnSpec]) -> None:
        """Приводит структуру к списку specs: добавление, удаление, переименование,
        порядок, тип, обязательность, значение по умолчанию, индексы — в одной транзакции."""
        self.ctx.session.require(P_TABLE_STRUCTURE)
        validate_specs(specs)
        with self.db.session() as s:
            t = s.get(UserTable, table_id)
            if t is None:
                raise NotFound("Таблица не найдена.")
            conn = s.connection()
            existing = {c.id: c for c in t.columns}
            keep_ids = {sp.id for sp in specs if sp.id is not None}
            for cid in keep_ids:
                if cid not in existing:
                    raise ValidationError("Структура таблицы изменилась. Обновите окно.")
            changes: list[str] = []
            # удаление
            for cid, c in list(existing.items()):
                if cid not in keep_ids:
                    Repo.drop_column(conn, t.physical_name, c.physical_name)
                    changes.append(f"удалён «{c.name}»")
                    t.columns.remove(c)
                    s.delete(c)
            s.flush()
            for pos, sp in enumerate(specs):
                if sp.id is None:
                    c = TableColumn(table_id=t.id, name=sp.name, type=sp.type, position=pos,
                                    required=sp.required, default_value=sp.default,
                                    options=jdumps(sp.options or {}), width=sp.width or 0,
                                    indexed=sp.indexed, physical_name=f"tmp_{pos}")
                    s.add(c)
                    s.flush()
                    c.physical_name = f"c_{c.id}"
                    s.flush()
                    Repo.add_column(conn, t.physical_name, c.physical_name, T.TYPES[c.type].sql)
                    if sp.default and sp.default not in SPECIAL_DEFAULTS:
                        Repo.fill_column(conn, t.physical_name, c.physical_name,
                                         T.to_storage(sp.type, sp.default, sp.options))
                    if sp.indexed:
                        Repo.create_index(conn, t.physical_name, c.physical_name)
                    changes.append(f"добавлен «{sp.name}»")
                    continue
                c = existing[sp.id]
                if c.name != sp.name:
                    changes.append(f"«{c.name}» → «{sp.name}»")
                    c.name = sp.name
                if c.type != sp.type:
                    self._convert_column(conn, t.physical_name, c, sp)
                    changes.append(f"тип «{sp.name}»: {T.TYPES[c.type].label} → "
                                   f"{T.TYPES[sp.type].label}")
                    c.type = sp.type
                elif c.type == T.CHOICE:
                    self._check_choices(conn, t.physical_name, c, sp)
                c.position = pos
                c.required = sp.required
                c.default_value = sp.default
                c.options = jdumps(sp.options or {})
                if sp.width:
                    c.width = sp.width
                if sp.indexed != c.indexed:
                    if sp.indexed:
                        Repo.create_index(conn, t.physical_name, c.physical_name)
                    else:
                        Repo.drop_index(conn, t.physical_name, c.physical_name)
                    c.indexed = sp.indexed
            t.updated_at = utcnow()
            s.flush()
            log_change(conn, self.ctx.session.username, "table_structure", t.id,
                       details={"changes": changes})

    @staticmethod
    def _check_choices(conn, table, col: TableColumn, sp: ColumnSpec) -> None:
        choices = sp.options.get("choices") or []
        if not choices or sp.options.get("allow_other"):
            return
        allowed = set(choices)
        bad = [v for _, v in Repo.column_values(conn, table, col.physical_name)
               if v not in allowed]
        if bad:
            raise ValidationError(
                f"Столбец «{sp.name}»: {len(bad)} значений не входят в новый список "
                f"(например, «{bad[0]}»). Добавьте их в список или разрешите другие значения.")

    @staticmethod
    def _convert_column(conn, table: str, col: TableColumn, sp: ColumnSpec) -> None:
        """Смена типа: все существующие значения должны успешно преобразоваться."""
        rows = Repo.column_values(conn, table, col.physical_name)
        old_opts = jloads(col.options, {}) or {}
        converted: list[tuple[int, object]] = []
        errors = 0
        example = ""
        for rid, val in rows:
            src = T.to_python(col.type, val) if col.type in (T.MONEY, T.DATE, T.TIME, T.DATETIME) \
                else (T.to_display(col.type, val) if col.type == T.BOOL else val)
            try:
                converted.append((rid, T.to_storage(sp.type, src, sp.options)))
            except ValueError as exc:
                errors += 1
                if not example:
                    example = f"«{T.to_display(col.type, val)}»: {exc}"
        if errors:
            raise ValidationError(
                f"Нельзя изменить тип столбца «{sp.name}»: {errors} значений не подходят "
                f"к типу «{T.TYPES[sp.type].label}». Например, {example}. Данные не изменены.")
        _ = old_opts
        # Новый столбец с нужным типом хранения, перенос значений, удаление старого
        tmp = f"{col.physical_name}_n"
        Repo.drop_index(conn, table, col.physical_name)
        Repo.add_column(conn, table, tmp, T.TYPES[sp.type].sql)
        conn.exec_driver_sql(
            f'UPDATE "{table}" SET "{tmp}" = ? WHERE "_id" = ?',
            [(v, rid) for rid, v in converted]) if converted else None
        Repo.drop_column(conn, table, col.physical_name)
        conn.exec_driver_sql(
            f'ALTER TABLE "{table}" RENAME COLUMN "{tmp}" TO "{col.physical_name}"')
        if col.indexed:
            Repo.create_index(conn, table, col.physical_name)

    def save_column_widths(self, table_id: int, widths: dict[int, int]) -> None:
        """Сохраняет ширину столбцов (настройка вида, доступна всем, кто может читать)."""
        self.ctx.session.require(P_DATA_READ)
        with self.db.session() as s:
            for c in s.scalars(select(TableColumn).where(TableColumn.table_id == table_id)):
                if c.id in widths:
                    c.width = int(widths[c.id])

    def reorder_columns(self, table_id: int, order: list[int]) -> None:
        self.ctx.session.require(P_TABLE_STRUCTURE)
        with self.db.session() as s:
            cols = {c.id: c for c in s.scalars(
                select(TableColumn).where(TableColumn.table_id == table_id))}
            for pos, cid in enumerate(order):
                if cid in cols:
                    cols[cid].position = pos

    # ── операции над таблицей ──────────────────────────────────────
    def rename(self, table_id: int, new_name: str) -> None:
        self.ctx.session.require(P_TABLE_STRUCTURE)
        new_name = self._check_name(new_name, exclude_id=table_id)
        with self.db.session() as s:
            t = self._get(s, table_id)
            old = t.name
            t.name = new_name
            t.updated_at = utcnow()
            log_change(s.connection(), self.ctx.session.username, "table_rename", table_id,
                       details={"old": old, "new": new_name})

    def copy(self, table_id: int, new_name: str, with_data: bool = True) -> int:
        self.ctx.session.require(P_TABLE_CREATE)
        src = self.get(table_id)
        new_name = self._check_name(new_name)
        specs = [ColumnSpec(name=c.name, type=c.type, required=c.required, default=c.default,
                            options=dict(c.options), indexed=c.indexed, width=c.width)
                 for c in src.columns]
        with self.db.session() as s:
            new_id = self._create_in_session(s, new_name, specs, src.kind, src.category_id,
                                             src.description)
            s.flush()
            if with_data:
                new_cols = [c.physical_name for c in sorted(
                    s.get(UserTable, new_id).columns, key=lambda c: c.position)]
                Repo.copy_data(s.connection(), src.physical, f"data_{new_id}",
                               [c.physical for c in src.columns], new_cols)
        return new_id

    def set_archived(self, table_id: int, archived: bool) -> None:
        self.ctx.session.require(P_TABLE_ARCHIVE)
        with self.db.session() as s:
            t = self._get(s, table_id)
            t.is_archived = archived
            log_change(s.connection(), self.ctx.session.username,
                       "table_archive" if archived else "table_restore", table_id,
                       details={"name": t.name})

    def delete_permanently(self, table_id: int) -> None:
        self.ctx.session.require(P_TABLE_DELETE)
        with self.db.session() as s:
            t = self._get(s, table_id)
            name, phys = t.name, t.physical_name
            conn = s.connection()
            Repo.drop_table(conn, phys)
            s.delete(t)
            s.flush()
            conn.execute(text("DELETE FROM wm_history WHERE table_id = :t AND row_id IS NOT NULL"),
                         {"t": table_id})
            log_change(conn, self.ctx.session.username, "table_delete", table_id,
                       details={"name": name})

    def update_settings(self, table_id: int, **values) -> None:
        self.ctx.session.require(P_DATA_READ)
        with self.db.session() as s:
            t = self._get(s, table_id)
            data = jloads(t.settings, {}) or {}
            data.update(values)
            t.settings = jdumps(data)

    def set_description(self, table_id: int, description: str) -> None:
        self.ctx.session.require(P_TABLE_STRUCTURE)
        with self.db.session() as s:
            self._get(s, table_id).description = (description or "")[:2000]

    @staticmethod
    def _get(s, table_id: int) -> UserTable:
        t = s.get(UserTable, table_id)
        if t is None:
            raise NotFound("Таблица не найдена.")
        return t

    # ── категории ──────────────────────────────────────────────────
    def categories(self) -> list[tuple[int, str]]:
        with self.db.session() as s:
            return [(c.id, c.name) for c in s.scalars(
                select(Category).order_by(Category.position, Category.name))]

    def create_category(self, name: str) -> int:
        self.ctx.session.require(P_TABLE_STRUCTURE)
        name = T.normalize_spaces(name or "")
        if not name or len(name) > MAX_NAME:
            raise ValidationError("Укажите название категории (до 200 символов).")
        with self.db.session() as s:
            for c in s.scalars(select(Category)):
                if c.name.casefold() == name.casefold():
                    return c.id
            pos = (s.scalar(select(func.max(Category.position))) or 0) + 1
            c = Category(name=name, position=pos)
            s.add(c)
            s.flush()
            return c.id

    def rename_category(self, cat_id: int, name: str) -> None:
        self.ctx.session.require(P_TABLE_STRUCTURE)
        name = T.normalize_spaces(name or "")
        if not name:
            raise ValidationError("Укажите название категории.")
        with self.db.session() as s:
            for c in s.scalars(select(Category)):
                if c.id != cat_id and c.name.casefold() == name.casefold():
                    raise ValidationError("Категория с таким названием уже есть.")
            c = s.get(Category, cat_id)
            if c:
                c.name = name

    def delete_category(self, cat_id: int) -> None:
        """Удаляет категорию; таблицы остаются (переходят в «Без категории»)."""
        self.ctx.session.require(P_TABLE_STRUCTURE)
        with self.db.session() as s:
            for t in s.scalars(select(UserTable).where(UserTable.category_id == cat_id)):
                t.category_id = None
            c = s.get(Category, cat_id)
            if c:
                s.delete(c)

    def set_category(self, table_id: int, cat_id: int | None) -> None:
        self.ctx.session.require(P_TABLE_STRUCTURE)
        with self.db.session() as s:
            self._get(s, table_id).category_id = cat_id

    # ── статистика ─────────────────────────────────────────────────
    def last_modified(self, info: TableInfo) -> dt.datetime:
        with self.db.connect() as conn:
            lm = Repo.last_modified(conn, info.physical)
        candidates = [info.updated_at]
        if lm:
            try:
                candidates.append(dt.datetime.fromisoformat(lm))
            except ValueError:
                pass
        return max(candidates)

    def history(self, table_id: int | None = None, limit: int = 200) -> list[dict]:
        self.ctx.session.require(P_DATA_READ)
        sql = "SELECT ts, username, table_id, row_id, action, details FROM wm_history"
        params: dict = {"lim": limit}
        if table_id is not None:
            sql += " WHERE table_id = :t"
            params["t"] = table_id
        sql += " ORDER BY id DESC LIMIT :lim"
        with self.db.connect() as conn:
            return [dict(ts=r[0], user=r[1], table_id=r[2], row_id=r[3], action=r[4],
                         details=jloads(r[5], {})) for r in conn.execute(text(sql), params)]


_ = now_str
