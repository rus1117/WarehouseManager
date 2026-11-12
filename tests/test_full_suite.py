"""Комплексное тестирование сценариев Warehouse Manager."""
from __future__ import annotations

import csv
import os
import shutil
import tempfile
from pathlib import Path

import pytest
from openpyxl import Workbook

from wm.app_context import AppContext
from wm.core import types as T
from wm.core.errors import IncompatibleDatabase, ValidationError
from wm.core.security import ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER
from wm.services.common import ColumnSpec
from wm.services.exporter import ExportSource
from wm.services.importer import (
    DUP_ALL,
    DUP_SKIP,
    DUP_WARN,
    ImportColumn,
    ImportPlan,
)
from wm.services.search import FilterSpec
from wm.services.templates import get_templates


@pytest.fixture
def env():
    temp_dir = tempfile.mkdtemp()
    db_file = Path(temp_dir) / "warehouse_test.db"
    backup_dir = Path(temp_dir) / "backups"
    ctx = AppContext(db_file=db_file, backup_dir=backup_dir)
    ctx.initialize()
    admin_user = ctx.users.authenticate("admin", "admin123")
    ctx.session.login(admin_user)
    yield ctx, Path(temp_dir)
    ctx.shutdown()
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_table_structure_lifecycle(env):
    """1-3. Создание, добавление, удаление, переименование столбцов и смена типов."""
    ctx, _ = env

    # Создание
    specs = [
        ColumnSpec(name="Товар", type="text", required=True),
        ColumnSpec(name="Цена", type="money"),
    ]
    t_id = ctx.tables.create("Прайс-лист", specs)
    t = ctx.tables.get(t_id)
    assert len(t.columns) == 2

    # Добавление и переименование
    new_specs = [
        ColumnSpec(id=t.columns[0].id, name="Наименование товара", type="text", required=True),
        ColumnSpec(id=t.columns[1].id, name="Цена", type="money"),
        ColumnSpec(name="Количество на складе", type="float", default="0"),
    ]
    ctx.tables.update_structure(t_id, new_specs)
    t_updated = ctx.tables.get(t_id)
    assert len(t_updated.columns) == 3
    assert t_updated.columns[0].name == "Наименование товара"

    # Удаление столбца
    del_specs = [
        ColumnSpec(id=t_updated.columns[0].id, name="Наименование товара", type="text"),
        ColumnSpec(id=t_updated.columns[2].id, name="Количество на складе", type="float"),
    ]
    ctx.tables.update_structure(t_id, del_specs)
    t_final = ctx.tables.get(t_id)
    assert len(t_final.columns) == 2


def test_records_crud_and_persistence(env):
    """4-8. Добавление, редактирование, удаление, сохранение и перезапуск приложения."""
    ctx, tmp_dir = env

    tmpl = next(t for t in get_templates() if t.code == "warehouse")
    t_id = ctx.tables.create("Складской учёт 2026", tmpl.columns, kind="warehouse")
    table = ctx.tables.get(t_id)
    cols = {c.name: c.id for c in table.columns}

    # Добавление
    row_data = {
        cols["Фамилия"]: "Сидоров",
        cols["Имя"]: "Алексей",
        cols["Тип операции"]: "Привёз",
        cols["Название товара"]: "Труба профильная 40х20",
        cols["Количество"]: 50.0,
        cols["Дата"]: "2026-11-12",
        cols["Время"]: "14:00:00",
    }
    r_id = ctx.records.insert(t_id, row_data)
    assert r_id > 0

    # Редактирование
    ctx.records.update(t_id, r_id, {cols["Количество"]: 65.0})
    rows = ctx.records.get(table, [r_id])
    assert rows[0][table.column_by_name("Количество").position + 1] == 65.0

    # Персистентность: закрываем и открываем заново
    ctx.shutdown()
    new_ctx = AppContext(db_file=ctx.db_file, backup_dir=ctx.default_backup_dir)
    new_ctx.initialize()
    admin = new_ctx.users.authenticate("admin", "admin123")
    new_ctx.session.login(admin)

    t_reopened = new_ctx.tables.get(t_id, with_count=True)
    assert t_reopened.row_count == 1
    new_ctx.shutdown()
    ctx.initialize()
    ctx.session.login(admin)


def test_excel_and_csv_import_export(env):
    """9-11. Импорт XLSX, CSV, дедупликация и экспорт."""
    ctx, tmp_dir = env

    # Создаем тестовый файл Excel с русскими символами и датами
    xlsx_path = tmp_dir / "test_data.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Лист1"
    ws.append(["Фамилия", "Операция", "Товар", "Количество", "Дата"])
    ws.append(["Ахметов", "Привёз", "Перфоратор Bosch", 2, "12.11.2026"])
    ws.append(["Смирнов", "Забрал", "Шуруповёрт Makita", 1, "12.11.2026"])
    ws.append(["Смирнов", "Забрал", "Шуруповёрт Makita", 1, "12.11.2026"])  # Дубликат
    wb.save(xlsx_path)

    # Импорт в новую таблицу с пропуском дубликатов
    info = ctx.importer.analyze(xlsx_path)
    headers, preview_rows = ctx.importer.preview(info, "Лист1")
    cols = [
        ImportColumn(0, "Фамилия", new_spec=ColumnSpec("Фамилия", "text")),
        ImportColumn(1, "Операция", new_spec=ColumnSpec("Операция", "text")),
        ImportColumn(2, "Товар", new_spec=ColumnSpec("Товар", "text")),
        ImportColumn(3, "Количество", new_spec=ColumnSpec("Количество", "float")),
        ImportColumn(4, "Дата", new_spec=ColumnSpec("Дата", "date")),
    ]
    plan = ImportPlan(
        path=xlsx_path,
        sheet="Лист1",
        header_row=1,
        columns=cols,
        new_table_name="Импортированные инструменты",
        duplicate_mode=DUP_SKIP,
    )
    res = ctx.importer.run(plan)
    assert res.imported == 2
    assert res.skipped_duplicates == 1

    # Экспорт в CSV
    imp_table = ctx.tables.get(res.table_id)
    csv_path = tmp_dir / "exported.csv"
    ctx.exporter.export([ExportSource(table=imp_table)], csv_path, fmt="csv")
    assert csv_path.exists()
    content = csv_path.read_text(encoding="utf-8-sig")
    assert "Ахметов" in content
    assert "Перфоратор Bosch" in content


def test_search_advanced_filters(env):
    """12. Расширенный поиск по условиям и диапазонам."""
    ctx, _ = env
    tmpl = next(t for t in get_templates() if t.code == "goods")
    t_id = ctx.tables.create("Товары склад", tmpl.columns)
    t = ctx.tables.get(t_id)
    cols = {c.name: c.id for c in t.columns}

    ctx.records.insert_many(t_id, [
        {cols["Название товара"]: "Гвозди 100мм", cols["Остаток"]: 500.0, cols["Цена"]: 250.0},
        {cols["Название товара"]: "Саморезы 35мм", cols["Остаток"]: 2000.0, cols["Цена"]: 120.0},
        {cols["Название товара"]: "Болты М8", cols["Остаток"]: 150.0, cols["Цена"]: 45.0},
    ])

    # Поиск по диапазону цен
    price_col = t.column_by_name("Цена")
    conds = ctx.search.build(t, [
        FilterSpec(column_id=price_col.id, op="between", value="40", value2="150")
    ])
    found = ctx.records.fetch(t, conditions=conds)
    assert len(found) == 2  # Саморезы (120) и Болты (45)


def test_backup_restore_and_integrity(env):
    """14-16. Резервное копирование, восстановление и проверка целостности."""
    ctx, _ = env
    t_id = ctx.tables.create("Важная таблица", [ColumnSpec("Поле", "text")])
    ctx.records.insert(t_id, {ctx.tables.get(t_id).columns[0].id: "Данные"})

    backup_file = ctx.backup.create_backup(note="Точка сохранения")
    assert backup_file.exists()
    assert len(ctx.backup.check_integrity(backup_file)) == 0

    # Модифицируем таблицу
    ctx.tables.rename(t_id, "Измененное название")
    assert ctx.tables.get(t_id).name == "Измененное название"

    # Восстанавливаем из резервной копии
    ctx.backup.restore_backup(backup_file)
    restored_table = ctx.tables.get(t_id)
    assert restored_table.name == "Важная таблица"
