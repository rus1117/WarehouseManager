"""Автоматическое GUI-тестирование всех вкладок, диалогов, тем, импорта, экспорта, бэкапов и таблиц."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from wm.app_context import AppContext
from wm.ui.dialogs.record_edit_dialog import RecordEditDialog
from wm.ui.dialogs.table_designer_dialog import TableDesignerDialog
from wm.ui.dialogs.user_management_dialog import UserEditDialog, UserManagementDialog
from wm.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)

    temp_dir = tempfile.mkdtemp()
    db_file = Path(temp_dir) / "ui_test.db"
    backup_dir = Path(temp_dir) / "backups"
    ctx = AppContext(db_file=db_file, backup_dir=backup_dir)
    ctx.initialize()
    ctx.session.login(ctx.users.authenticate("admin", "admin123"))

    win = MainWindow(ctx)
    yield win, ctx, Path(temp_dir)
    win.close()
    ctx.shutdown()
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_navigation_and_table_creation(window):
    win, ctx, _ = window

    # 1. Проверяем переключение всех 8 разделов в сайдбаре
    win.btn_dashboard.click()
    assert win.stack.currentWidget() == win.view_dashboard

    win.btn_tables.click()
    assert win.stack.currentWidget() == win.view_tables

    win.btn_create.click()
    assert win.stack.currentWidget() == win.view_create

    win.btn_search.click()
    assert win.stack.currentWidget() == win.view_search

    win.btn_import.click()
    assert win.stack.currentWidget() == win.view_import

    win.btn_export.click()
    assert win.stack.currentWidget() == win.view_export

    win.btn_backup.click()
    assert win.stack.currentWidget() == win.view_backup

    win.btn_settings.click()
    assert win.stack.currentWidget() == win.view_settings

    # 2. Создание таблицы через вкладку "Создать таблицу" (плюс добавление/перемещение/удаление столбца)
    win.btn_create.click()
    initial_cols = win.view_create.cols_table.rowCount()
    win.view_create._add_empty_column()
    assert win.view_create.cols_table.rowCount() == initial_cols + 1
    win.view_create.cols_table.selectRow(initial_cols)
    win.view_create._move_column(-1)
    assert win.view_create.cols_table.currentRow() == initial_cols - 1
    win.view_create._delete_column()
    assert win.view_create.cols_table.rowCount() == initial_cols

    win.view_create._create_table()
    assert win.tab_widget.count() == 2
    assert win.tab_widget.currentIndex() == 1

    # 3. Добавление записи через диалог RecordEditDialog
    editor = win.tab_widget.currentWidget()
    rec_dlg = RecordEditDialog(ctx, editor.table, parent=win)
    cols = {c.name: c.id for c in editor.table.columns}
    rec_dlg.widgets[cols["Фамилия"]].setText("Иванов")
    rec_dlg.widgets[cols["Имя"]].setText("Пётр")
    rec_dlg.widgets[cols["Название товара"]].setText("Трансформатор")
    rec_dlg.widgets[cols["Количество"]].setValue(25)
    assert rec_dlg._save() is True
    editor.refresh()
    assert editor.model.rowCount() == 1

    # 4. Inline-редактирование ячейки в таблице
    idx = editor.model.index(0, 1)  # Фамилия
    assert editor.model.setData(idx, "Сидоров", Qt.ItemDataRole.EditRole) is True
    assert editor.model.data(idx) == "Сидоров"

    # 5. Быстрый поиск и сортировка в редакторе таблицы
    editor.search_input.setText("Сидоров")
    assert editor.model.rowCount() == 1
    editor.search_input.setText("Несуществующий")
    assert editor.model.rowCount() == 0
    editor.search_input.clear()
    assert editor.model.rowCount() == 1
    editor._on_header_clicked(1)

    # 6. Глобальный поиск через SearchView
    win.btn_search.click()
    win.view_search.query_input.setText("Сидоров")
    win.view_search._do_search()
    assert win.view_search.results_table.rowCount() == 1

    # 7. Экспорт в XLSX и CSV через ExportView
    win.btn_export.click()
    xlsx_out = Path(tempfile.gettempdir()) / "wm_ui_test_export.xlsx"
    win.view_export.dest_path_input.setText(str(xlsx_out))
    win.view_export.fmt_xlsx_radio.setChecked(True)
    win.view_export._do_export()
    assert xlsx_out.exists()

    # 8. Импорт обратно через ImportView
    win.btn_import.click()
    win.view_import.file_path_input.setText(str(xlsx_out))
    win.view_import.file_info = ctx.importer.analyze(xlsx_out)
    win.view_import.sheet_combo.clear()
    for s in win.view_import.file_info.sheets:
        win.view_import.sheet_combo.addItem(s.name, s.name)
    win.view_import.new_table_name_input.setText("Импортированная таблица")
    win.view_import._load_preview()
    win.view_import._do_import()
    assert any(t.name == "Импортированная таблица" for t in ctx.tables.list())
    xlsx_out.unlink(missing_ok=True)

    # 9. Резервное копирование и проверка целостности через BackupView
    win.btn_backup.click()
    win.view_backup.note_input.setText("Тестовый бэкап")
    win.view_backup._create_backup()
    assert win.view_backup.table.rowCount() >= 1
    win.view_backup._check_integrity()

    # 10. Переключение тем (Светлая / Тёмная) и сохранение настроек
    win.btn_settings.click()
    win.view_settings.theme_combo.setCurrentIndex(1)  # dark
    assert ctx.settings.get("theme") == "dark"
    win.view_settings.theme_combo.setCurrentIndex(0)  # light
    assert ctx.settings.get("theme") == "light"
    win.view_settings._save_settings()

    # 11. Диалог управления пользователями
    usr_dlg = UserManagementDialog(ctx, parent=win)
    assert usr_dlg.table.rowCount() >= 1
    usr_dlg.close()

    # 12. Диалог структуры таблицы
    des_dlg = TableDesignerDialog(ctx, table_id=editor.table.id, parent=win)
    des_dlg._add_empty_column()
    des_dlg._on_save()
    assert len(ctx.tables.get(editor.table.id).columns) == initial_cols + 1

    # 13. Копирование, архивация и удаление таблицы в разделе "Мои таблицы"
    win.btn_tables.click()
    win.view_tables.table_widget.selectRow(0)
    win.view_tables._copy_selected()
    assert len(ctx.tables.list()) >= 3
    win.view_tables.table_widget.selectRow(0)
    win.view_tables._delete_selected()
