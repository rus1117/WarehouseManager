import os
import shutil
import tempfile
from pathlib import Path
import pytest

from wm.app_context import AppContext
from wm.core.security import ROLE_ADMIN, ROLE_OPERATOR
from wm.services.templates import get_templates
from wm.services.importer import ImportPlan, ImportColumn
from wm.services.exporter import ExportSource


@pytest.fixture
def temp_ctx():
    temp_dir = tempfile.mkdtemp()
    db_file = Path(temp_dir) / "test.db"
    backup_dir = Path(temp_dir) / "backups"
    ctx = AppContext(db_file=db_file, backup_dir=backup_dir)
    ctx.initialize()
    user = ctx.users.authenticate("admin", "admin123")
    ctx.session.login(user)
    yield ctx
    ctx.shutdown()
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_core_workflow(temp_ctx):
    ctx = temp_ctx
    # 1. Шаблоны и создание таблицы
    tmpl = next(t for t in get_templates() if t.code == "warehouse")
    t_id = ctx.tables.create("Склад ноябрь", tmpl.columns, kind="warehouse")
    table = ctx.tables.get(t_id, with_count=True)
    assert table.name == "Склад ноябрь"
    assert table.row_count == 0

    # 2. Добавление записей
    cols = {c.name: c.id for c in table.columns}
    row1 = {
        cols["Фамилия"]: "Иванов",
        cols["Имя"]: "Иван",
        cols["Тип операции"]: "Привёз",
        cols["Название товара"]: "Кабель медный 3х2.5",
        cols["Количество"]: 100.5,
        cols["Дата"]: "2026-11-12",
        cols["Время"]: "10:30:00",
        cols["Комментарий"]: "Партия 1"
    }
    row2 = {
        cols["Фамилия"]: "Петров",
        cols["Имя"]: "Петр",
        cols["Тип операции"]: "Забрал",
        cols["Название товара"]: "Кабель медный 3х2.5",
        cols["Количество"]: 30.0,
        cols["Дата"]: "2026-11-12",
        cols["Время"]: "11:00:00",
        cols["Комментарий"]: "Выдано в монтаж"
    }
    r_ids = ctx.records.insert_many(t_id, [row1, row2])
    assert len(r_ids) == 2
    assert ctx.records.count(table) == 2

    # 3. Поиск
    found = ctx.records.fetch(table, quick="Иванов")
    assert len(found) == 1
    assert "Иванов" in str(found[0])

    # 4. Экспорт в XLSX
    export_xlsx = ctx.default_backup_dir / "export_test.xlsx"
    ctx.exporter.export([ExportSource(table=table)], export_xlsx, fmt="xlsx")
    assert export_xlsx.exists() and export_xlsx.stat().st_size > 0

    # 5. Экспорт в CSV
    export_csv = ctx.default_backup_dir / "export_test.csv"
    ctx.exporter.export([ExportSource(table=table)], export_csv, fmt="csv")
    assert export_csv.exists() and export_csv.stat().st_size > 0

    # 6. Резервное копирование и целостность
    backup_path = ctx.backup.create_backup(note="Тестовый бэкап")
    assert backup_path.exists()
    problems = ctx.backup.check_integrity(backup_path)
    assert len(problems) == 0

    # 7. Проверка прав: создадим оператора и проверим, что он не может удалять таблицу окончательно
    op_id = ctx.users.create_user("operator1", "Оператор Иванов", "pass123", ROLE_OPERATOR)
    op_user = ctx.users.authenticate("operator1", "pass123")
    ctx.session.login(op_user)
    with pytest.raises(Exception):
        ctx.tables.delete_permanently(t_id)  # оператору запрещено окончательное удаление
