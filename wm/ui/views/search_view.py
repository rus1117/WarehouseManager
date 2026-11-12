"""Раздел глобального и расширенного поиска по всем таблицам."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from wm.core.errors import WMError
from wm.ui.common import show_error, show_info

if TYPE_CHECKING:
    from wm.app_context import AppContext


class SearchView(QWidget):
    def __init__(
        self,
        ctx: "AppContext",
        on_open_table: Callable[[int], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PageView")
        self.ctx = ctx
        self.on_open_table = on_open_table

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        header = QLabel("Поиск по всем таблицам")
        header.setProperty("class", "PageTitle")
        layout.addWidget(header)

        sub = QLabel("Введите поисковый запрос (слово, ФИО, номер, дату или название товара) для сквозного поиска:")
        sub.setProperty("class", "PageSubtitle")
        layout.addWidget(sub)

        # Строка поиска
        search_box = QHBoxLayout()
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Например: Иванов или Кабель или 12.11.2026...")
        self.query_input.setClearButtonEnabled(True)
        self.query_input.setMinimumHeight(34)
        self.query_input.returnPressed.connect(self._do_search)
        search_box.addWidget(self.query_input)

        search_btn = QPushButton("🔍 Найти")
        search_btn.setProperty("class", "Primary")
        search_btn.setMinimumHeight(34)
        search_btn.clicked.connect(self._do_search)
        search_box.addWidget(search_btn)

        reset_btn = QPushButton("Сбросить")
        reset_btn.setMinimumHeight(34)
        reset_btn.clicked.connect(self._reset)
        search_box.addWidget(reset_btn)

        layout.addLayout(search_box)

        self.summary_label = QLabel()
        self.summary_label.setProperty("class", "SectionTitle")
        layout.addWidget(self.summary_label)

        # Результаты поиска
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels([
            "Таблица", "№ строки", "Найденные данные", "Действие"
        ])
        self.results_table.setAlternatingRowColors(True)
        self.results_table.verticalHeader().setDefaultSectionSize(36)
        self.results_table.verticalHeader().setMinimumWidth(34)
        hh = self.results_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(0, 180)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(1, 90)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(3, 120)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.results_table, stretch=1)

    def _reset(self) -> None:
        self.query_input.clear()
        self.results_table.setRowCount(0)
        self.summary_label.clear()

    def _do_search(self) -> None:
        q = self.query_input.text().strip()
        if not q:
            self._reset()
            return

        try:
            results = self.ctx.search.global_search(q, limit_per_table=100)
            self.results_table.setRowCount(0)

            total_found = sum(count for _, count, _ in results)
            self.summary_label.setText(f"Найдено совпадений: {total_found}")

            row_idx = 0
            for table, count, rows in results:
                for r in rows:
                    self.results_table.insertRow(row_idx)
                    self.results_table.setRowHeight(row_idx, 36)
                    # 0. Имя таблицы
                    t_item = QTableWidgetItem(table.name)
                    t_item.setData(Qt.ItemDataRole.UserRole, table.id)
                    self.results_table.setItem(row_idx, 0, t_item)
                    # 1. ID строки
                    row_id = r[0]
                    id_item = QTableWidgetItem(str(row_id))
                    id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.results_table.setItem(row_idx, 1, id_item)
                    # 2. Содержимое
                    text_parts = []
                    for col, val in zip(table.columns, r[1:]):
                        if val is not None and str(val).strip():
                            text_parts.append(f"{col.name}: {val}")
                    content_str = " | ".join(text_parts)
                    self.results_table.setItem(row_idx, 2, QTableWidgetItem(content_str))

                    # 3. Кнопка «Открыть»
                    open_btn = QPushButton("Открыть")
                    tid = table.id
                    open_btn.clicked.connect(lambda _, x=tid: self.on_open_table(x))
                    self.results_table.setCellWidget(row_idx, 3, open_btn)

                    row_idx += 1

            if total_found == 0:
                show_info(self, "Поиск", "Ничего не найдено.")
        except WMError as exc:
            show_error(self, "Ошибка поиска", str(exc))

    def _on_double_click(self, index) -> None:
        tid = self.results_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        if tid:
            self.on_open_table(tid)
