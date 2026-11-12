"""Виджет просмотра и редактирования таблицы."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from wm.core.errors import WMError
from wm.services.common import TableInfo
from wm.ui.common import confirm_dialog, show_error, show_info, show_warning
from wm.ui.dialogs.record_edit_dialog import RecordEditDialog
from wm.ui.dialogs.table_designer_dialog import TableDesignerDialog
from wm.ui.models.table_model import TableRecordsModel

if TYPE_CHECKING:
    from wm.app_context import AppContext


class TableEditorView(QWidget):
    def __init__(self, ctx: "AppContext", table_id: int, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PageView")
        self.ctx = ctx
        self.table_id = table_id
        self.table: TableInfo = self.ctx.tables.get(table_id)

        self.model = TableRecordsModel(self.ctx, self.table, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Верхняя панель: Название, Быстрый поиск, Кнопки действий
        top_bar = QHBoxLayout()

        self.title_label = QLabel(self.table.name)
        self.title_label.setProperty("class", "PageTitle")
        top_bar.addWidget(self.title_label)

        top_bar.addSpacing(16)

        # Быстрый поиск
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Быстрый поиск по всем колонкам...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_changed)
        self.search_input.setMaximumWidth(280)
        top_bar.addWidget(self.search_input)

        top_bar.addStretch()

        add_btn = QPushButton("＋ Добавить запись")
        add_btn.setProperty("class", "Primary")
        add_btn.clicked.connect(self._add_record)
        top_bar.addWidget(add_btn)

        edit_rec_btn = QPushButton("✏️ Редактировать")
        edit_rec_btn.clicked.connect(self._edit_selected_record)
        top_bar.addWidget(edit_rec_btn)

        del_rec_btn = QPushButton("🗑️ Удалить")
        del_rec_btn.setProperty("class", "Danger")
        del_rec_btn.clicked.connect(self._delete_selected_records)
        top_bar.addWidget(del_rec_btn)

        edit_struct_btn = QPushButton("⚙️ Структура")
        edit_struct_btn.clicked.connect(self._edit_structure)
        top_bar.addWidget(edit_struct_btn)

        refresh_btn = QPushButton("🔄 Обновить")
        refresh_btn.clicked.connect(self.refresh)
        top_bar.addWidget(refresh_btn)

        layout.addLayout(top_bar)

        # Таблица
        self.table_view = QTableView()
        self.table_view.setModel(self.model)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.table_view.verticalHeader().setDefaultSectionSize(34)
        self.table_view.verticalHeader().setMinimumWidth(34)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSortIndicatorShown(True)
        self.table_view.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table_view.horizontalHeader().sectionResized.connect(self._on_column_resized)
        self.table_view.doubleClicked.connect(self._on_double_click)

        # Контекстное меню
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._open_context_menu)

        layout.addWidget(self.table_view, stretch=1)

        # Нижняя панель пагинации и статистики
        bottom_bar = QHBoxLayout()

        self.status_label = QLabel()
        self.status_label.setProperty("class", "PageSubtitle")
        bottom_bar.addWidget(self.status_label)

        bottom_bar.addStretch()

        self.prev_btn = QPushButton("◀ Назад")
        self.prev_btn.clicked.connect(self._prev_page)
        bottom_bar.addWidget(self.prev_btn)

        self.page_label = QLabel("Стр. 1")
        bottom_bar.addWidget(self.page_label)

        self.next_btn = QPushButton("Вперёд ▶")
        self.next_btn.clicked.connect(self._next_page)
        bottom_bar.addWidget(self.next_btn)

        layout.addLayout(bottom_bar)

        self.refresh()

    def refresh(self) -> None:
        self.table = self.ctx.tables.get(self.table_id)
        self.title_label.setText(self.table.name)
        self.model.table = self.table
        self.model.reload()
        self._apply_column_widths()
        self._update_pagination_ui()

    def _apply_column_widths(self) -> None:
        header = self.table_view.horizontalHeader()
        header.blockSignals(True)
        try:
            self.table_view.setColumnWidth(0, 60)
            for idx, col in enumerate(self.table.columns, 1):
                w = col.width if col.width and col.width > 30 else 150
                self.table_view.setColumnWidth(idx, w)
        finally:
            header.blockSignals(False)

    def _on_column_resized(self, section: int, _old: int, new_size: int) -> None:
        if section > 0 and section - 1 < len(self.table.columns) and new_size > 20:
            col = self.table.columns[section - 1]
            try:
                self.ctx.tables.save_column_widths(self.table.id, {col.id: new_size})
            except Exception:
                pass

    def _update_pagination_ui(self) -> None:
        total = self.model.total_count
        page = self.model.page
        limit = self.model.limit
        max_page = max(0, (total - 1) // limit) if total > 0 else 0

        start = page * limit + 1 if total > 0 else 0
        end = min((page + 1) * limit, total)
        self.status_label.setText(f"Записей: {total} (показано {start}–{end})")
        self.page_label.setText(f"Стр. {page + 1} из {max_page + 1}")
        self.prev_btn.setEnabled(page > 0)
        self.next_btn.setEnabled(page < max_page)

    def _prev_page(self) -> None:
        if self.model.page > 0:
            self.model.set_page(self.model.page - 1)
            self._update_pagination_ui()

    def _next_page(self) -> None:
        total = self.model.total_count
        max_page = max(0, (total - 1) // self.model.limit) if total > 0 else 0
        if self.model.page < max_page:
            self.model.set_page(self.model.page + 1)
            self._update_pagination_ui()

    def _on_search_changed(self, text: str) -> None:
        self.model.set_filter(self.model.conditions, text.strip())
        self._update_pagination_ui()

    def _on_header_clicked(self, section: int) -> None:
        if section == 0:
            self.model.set_sorting(None, not self.model.sort_desc)
        else:
            col = self.table.columns[section - 1]
            desc = not self.model.sort_desc if self.model.sort_col_id == col.id else False
            self.model.set_sorting(col.id, desc)

    def _selected_row_ids(self) -> list[int]:
        selected_indexes = self.table_view.selectionModel().selectedRows()
        row_ids = []
        for idx in selected_indexes:
            rid = self.model.get_row_id(idx.row())
            if rid is not None:
                row_ids.append(rid)
        return row_ids

    def _add_record(self) -> None:
        while True:
            dlg = RecordEditDialog(self.ctx, self.table, parent=self)
            res = dlg.exec()
            if res == QDialog.DialogCode.Accepted:
                self.refresh()
                if not dlg.add_another:
                    break
            else:
                break

    def _edit_selected_record(self) -> None:
        ids = self._selected_row_ids()
        if not ids:
            show_warning(self, "Внимание", "Выберите запись для редактирования.")
            return
        row_id = ids[0]
        # Читаем существующие данные строки
        rows = self.ctx.records.get(self.table, [row_id])
        if not rows:
            return
        initial_data = {c.id: v for c, v in zip(self.table.columns, rows[0][1:])}
        dlg = RecordEditDialog(self.ctx, self.table, row_id=row_id, initial_data=initial_data, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _delete_selected_records(self) -> None:
        ids = self._selected_row_ids()
        if not ids:
            show_warning(self, "Внимание", "Выберите записи для удаления.")
            return
        if not confirm_dialog(
            self,
            "Подтверждение удаления",
            f"Вы уверены, что хотите удалить выбранные записи ({len(ids)} шт.)?",
        ):
            return
        try:
            self.ctx.records.delete(self.table.id, ids)
            self.refresh()
            show_info(self, "Успех", f"Удалено записей: {len(ids)}.")
        except WMError as exc:
            show_error(self, "Ошибка удаления", str(exc))

    def _copy_selected_records(self) -> None:
        ids = self._selected_row_ids()
        if not ids:
            return
        try:
            new_ids = self.ctx.records.duplicate(self.table.id, ids)
            self.refresh()
            show_info(self, "Успех", f"Скопировано записей: {len(new_ids)}.")
        except WMError as exc:
            show_error(self, "Ошибка копирования", str(exc))

    def _edit_structure(self) -> None:
        dlg = TableDesignerDialog(self.ctx, table_id=self.table.id, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _on_double_click(self, index) -> None:
        if index.column() == 0:
            self._edit_selected_record()

    def _open_context_menu(self, pos) -> None:
        menu = QMenu(self)
        add_act = menu.addAction("Добавить запись")
        add_act.triggered.connect(self._add_record)

        if self._selected_row_ids():
            edit_act = menu.addAction("Редактировать запись")
            edit_act.triggered.connect(self._edit_selected_record)

            copy_act = menu.addAction("Дублировать запись")
            copy_act.triggered.connect(self._copy_selected_records)

            menu.addSeparator()

            del_act = menu.addAction("Удалить выбранные")
            del_act.triggered.connect(self._delete_selected_records)

        menu.exec(self.table_view.viewport().mapToGlobal(pos))
