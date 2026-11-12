"""Раздел «Мои таблицы»."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from wm.core.errors import WMError
from wm.services.common import TableInfo
from wm.ui.common import confirm_dialog, show_error, show_info, show_warning

if TYPE_CHECKING:
    from wm.app_context import AppContext


class TablesView(QWidget):
    def __init__(
        self,
        ctx: "AppContext",
        on_open_table: Callable[[int], None],
        on_create_table: Callable[[], None],
        on_table_deleted: Callable[[int], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PageView")
        self.ctx = ctx
        self.on_open_table = on_open_table
        self.on_create_table = on_create_table
        self.on_table_deleted = on_table_deleted
        self.show_archived = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Верхняя панель управления
        top_bar = QHBoxLayout()

        title_lbl = QLabel("Мои таблицы")
        title_lbl.setProperty("class", "PageTitle")
        top_bar.addWidget(title_lbl)

        top_bar.addSpacing(20)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Фильтр по названию...")
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.textChanged.connect(self._apply_filter)
        self.filter_input.setMaximumWidth(260)
        top_bar.addWidget(self.filter_input)

        self.archive_combo = QComboBox()
        self.archive_combo.addItem("Активные таблицы", False)
        self.archive_combo.addItem("Архивные таблицы", True)
        self.archive_combo.currentIndexChanged.connect(self._on_archive_toggle)
        top_bar.addWidget(self.archive_combo)

        top_bar.addStretch()

        create_btn = QPushButton("＋ Создать таблицу")
        create_btn.setProperty("class", "Primary")
        create_btn.clicked.connect(self.on_create_table)
        top_bar.addWidget(create_btn)

        layout.addLayout(top_bar)

        # Список таблиц (табличный вид)
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(6)
        self.table_widget.setHorizontalHeaderLabels([
            "ID", "Название таблицы", "Категория", "Тип", "Записей", "Последнее изменение"
        ])
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.verticalHeader().setDefaultSectionSize(36)
        self.table_widget.verticalHeader().setMinimumWidth(34)
        hh = self.table_widget.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(0, 60)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(2, 150)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(3, 140)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(4, 95)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(5, 160)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_widget.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_widget.doubleClicked.connect(self._on_double_click)

        # Контекстное меню
        self.table_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self._open_context_menu)

        layout.addWidget(self.table_widget, stretch=1)

        # Нижняя панель действий
        bottom_bar = QHBoxLayout()

        open_btn = QPushButton("📂 Открыть")
        open_btn.setProperty("class", "Primary")
        open_btn.clicked.connect(self._open_selected)
        bottom_bar.addWidget(open_btn)

        copy_btn = QPushButton("📋 Создать копию")
        copy_btn.clicked.connect(self._copy_selected)
        bottom_bar.addWidget(copy_btn)

        self.archive_btn = QPushButton("📦 В архив")
        self.archive_btn.clicked.connect(self._toggle_archive_selected)
        bottom_bar.addWidget(self.archive_btn)

        delete_btn = QPushButton("🗑️ Удалить навсегда")
        delete_btn.setProperty("class", "Danger")
        delete_btn.clicked.connect(self._delete_selected)
        bottom_bar.addWidget(delete_btn)

        bottom_bar.addStretch()

        refresh_btn = QPushButton("🔄 Обновить")
        refresh_btn.clicked.connect(self.refresh)
        bottom_bar.addWidget(refresh_btn)

        layout.addLayout(bottom_bar)

        self.tables_list: list[TableInfo] = []
        self.refresh()

    def refresh(self) -> None:
        self.tables_list = self.ctx.tables.list(
            include_archived=self.show_archived,
            archived_only=self.show_archived,
            with_counts=True,
        )
        self._apply_filter()

    def _apply_filter(self) -> None:
        needle = self.filter_input.text().strip().lower()
        filtered = [
            t for t in self.tables_list
            if not needle or needle in t.name.lower() or (t.category and needle in t.category.lower())
        ]
        self.table_widget.setRowCount(len(filtered))
        for r, t in enumerate(filtered):
            id_item = QTableWidgetItem(str(t.id))
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            id_item.setData(Qt.ItemDataRole.UserRole, t.id)
            self.table_widget.setItem(r, 0, id_item)

            self.table_widget.setItem(r, 1, QTableWidgetItem(t.name))
            self.table_widget.setItem(r, 2, QTableWidgetItem(t.category or "—"))

            kind_str = "Складской учёт" if t.kind == "warehouse" else "Универсальная"
            self.table_widget.setItem(r, 3, QTableWidgetItem(kind_str))

            cnt_item = QTableWidgetItem(str(t.row_count or 0))
            cnt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_widget.setItem(r, 4, cnt_item)

            date_str = t.updated_at.strftime("%d.%m.%Y %H:%M") if t.updated_at else ""
            date_item = QTableWidgetItem(date_str)
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_widget.setItem(r, 5, date_item)

    def _on_archive_toggle(self, index: int) -> None:
        self.show_archived = self.archive_combo.currentData()
        self.archive_btn.setText("📦 Восстановить из архива" if self.show_archived else "📦 В архив")
        self.refresh()

    def _selected_table_id(self) -> int | None:
        r = self.table_widget.currentRow()
        if r < 0:
            return None
        return self.table_widget.item(r, 0).data(Qt.ItemDataRole.UserRole)

    def _on_double_click(self) -> None:
        self._open_selected()

    def _open_selected(self) -> None:
        tid = self._selected_table_id()
        if tid is not None:
            self.on_open_table(tid)
        else:
            show_warning(self, "Внимание", "Выберите таблицу для открытия.")

    def _copy_selected(self) -> None:
        tid = self._selected_table_id()
        if not tid:
            show_warning(self, "Внимание", "Выберите таблицу для копирования.")
            return
        t = self.ctx.tables.get(tid)
        new_name = self.ctx.tables.unique_name(f"{t.name} (Копия)")
        try:
            self.ctx.tables.copy(tid, new_name, with_data=True)
            self.refresh()
            show_info(self, "Успех", f"Создана копия таблицы: «{new_name}».")
        except WMError as exc:
            show_error(self, "Ошибка копирования", str(exc))

    def _toggle_archive_selected(self) -> None:
        tid = self._selected_table_id()
        if not tid:
            show_warning(self, "Внимание", "Выберите таблицу из списка.")
            return
        t = self.ctx.tables.get(tid)
        action_name = "восстановить из архива" if t.archived else "переместить в архив"
        if not confirm_dialog(
            self,
            "Подтверждение",
            f"Вы уверены, что хотите {action_name} таблицу «{t.name}»?",
        ):
            return
        try:
            self.ctx.tables.set_archived(tid, not t.archived)
            self.refresh()
        except WMError as exc:
            show_error(self, "Ошибка изменения статуса", str(exc))

    def _delete_selected(self) -> None:
        tid = self._selected_table_id()
        if not tid:
            show_warning(self, "Внимание", "Выберите таблицу для удаления.")
            return
        t = self.ctx.tables.get(tid)
        if not confirm_dialog(
            self,
            "ВНИМАНИЕ: Окончательное удаление",
            f"Таблица «{t.name}» и ВСЕ её записи будут удалены БЕЗВОЗВРАТНО!\nПродолжить?",
        ):
            return
        try:
            self.ctx.tables.delete_permanently(tid)
            if self.on_table_deleted:
                self.on_table_deleted(tid)
            self.refresh()
            show_info(self, "Успех", f"Таблица «{t.name}» удалена.")
        except WMError as exc:
            show_error(self, "Ошибка удаления", str(exc))

    def _open_context_menu(self, pos) -> None:
        tid = self._selected_table_id()
        if not tid:
            return
        menu = QMenu(self)
        open_act = menu.addAction("Открыть таблицу")
        open_act.triggered.connect(self._open_selected)

        copy_act = menu.addAction("Создать копию")
        copy_act.triggered.connect(self._copy_selected)

        archive_act = menu.addAction("Восстановить" if self.show_archived else "В архив")
        archive_act.triggered.connect(self._toggle_archive_selected)

        menu.addSeparator()

        del_act = menu.addAction("Удалить навсегда")
        del_act.triggered.connect(self._delete_selected)

        menu.exec(self.table_widget.viewport().mapToGlobal(pos))
