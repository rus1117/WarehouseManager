"""Визуальный конструктор и редактор структуры таблиц."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
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

from wm.core import types as T
from wm.core.errors import WMError
from wm.services.common import ColumnSpec
from wm.services.templates import get_templates, warehouse_columns
from wm.ui.common import show_error, show_warning

if TYPE_CHECKING:
    from wm.app_context import AppContext


class TableDesignerDialog(QDialog):
    def __init__(
        self,
        ctx: "AppContext",
        table_id: int | None = None,
        is_warehouse_mode: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.table_id = table_id
        self.is_new = table_id is None
        self.is_warehouse_mode = is_warehouse_mode
        self.created_table_id: int | None = None

        title = "Создать новую таблицу" if self.is_new else "Структура таблицы"
        if is_warehouse_mode and self.is_new:
            title = "Создание складской таблицы"
        self.setWindowTitle(title)
        self.resize(840, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Верхняя панель: Название, Категория, Шаблоны
        top_form = QFormLayout()
        top_form.setSpacing(8)
        top_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.name_input = QLineEdit()
        self.name_input.setMinimumHeight(30)
        self.name_input.setPlaceholderText("Например, Склад ноябрь 2026")
        top_form.addRow("Название таблицы*:", self.name_input)

        self.category_combo = QComboBox()
        self.category_combo.setMinimumHeight(30)
        self.category_combo.addItem("— Без категории —", None)
        for cid, cname in self.ctx.tables.categories():
            self.category_combo.addItem(cname, cid)
        top_form.addRow("Категория / Папка:", self.category_combo)

        if self.is_new:
            self.template_combo = QComboBox()
            self.template_combo.setMinimumHeight(30)
            self.templates = get_templates()
            for tmpl in self.templates:
                self.template_combo.addItem(tmpl.title, tmpl.code)
            if self.is_warehouse_mode:
                self.template_combo.setCurrentText("Складской учёт")
            self.template_combo.currentIndexChanged.connect(self._on_template_selected)
            top_form.addRow("Шаблон:", self.template_combo)

        layout.addLayout(top_form)

        # Заголовок списка столбцов и кнопки перемещения
        col_header_layout = QHBoxLayout()
        col_title = QLabel("Столбцы таблицы:")
        col_title.setProperty("class", "SectionTitle")
        col_header_layout.addWidget(col_title)
        col_header_layout.addStretch()

        add_col_btn = QPushButton("＋ Добавить столбец")
        add_col_btn.clicked.connect(self._add_empty_column)
        col_header_layout.addWidget(add_col_btn)

        del_col_btn = QPushButton("🗑️ Удалить столбец")
        del_col_btn.clicked.connect(self._delete_column)
        col_header_layout.addWidget(del_col_btn)

        up_col_btn = QPushButton("▲ Вверх")
        up_col_btn.clicked.connect(lambda: self._move_column(-1))
        col_header_layout.addWidget(up_col_btn)

        down_col_btn = QPushButton("▼ Вниз")
        down_col_btn.clicked.connect(lambda: self._move_column(1))
        col_header_layout.addWidget(down_col_btn)

        layout.addLayout(col_header_layout)

        # Таблица столбцов
        self.cols_table = QTableWidget()
        self.cols_table.setColumnCount(5)
        self.cols_table.setHorizontalHeaderLabels([
            "Имя столбца", "Тип данных", "Обязательное", "По умолчанию", "Быстрый поиск"
        ])
        self.cols_table.setAlternatingRowColors(True)
        self.cols_table.verticalHeader().setDefaultSectionSize(36)
        self.cols_table.verticalHeader().setMinimumWidth(34)
        hh = self.cols_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(1, 175)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(2, 115)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(3, 140)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(4, 130)
        self.cols_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cols_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.cols_table, stretch=1)

        # Нижняя панель кнопок
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Создать таблицу" if self.is_new else "Сохранить изменения")
        save_btn.setProperty("class", "Primary")
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

        if not self.is_new and self.table_id is not None:
            self._load_existing_table(self.table_id)
        elif self.is_warehouse_mode:
            self._apply_specs(warehouse_columns())
            self.name_input.setText(self.ctx.tables.unique_name("Складской учёт"))
        else:
            self._on_template_selected()

    def _load_existing_table(self, table_id: int) -> None:
        table = self.ctx.tables.get(table_id)
        self.name_input.setText(table.name)
        if table.category_id:
            idx = self.category_combo.findData(table.category_id)
            if idx >= 0:
                self.category_combo.setCurrentIndex(idx)
        specs = [
            ColumnSpec(
                id=c.id,
                name=c.name,
                type=c.type,
                required=c.required,
                default=c.default,
                indexed=c.indexed,
                options=c.options,
            )
            for c in table.columns
        ]
        self._apply_specs(specs)

    def _apply_specs(self, specs: list[ColumnSpec]) -> None:
        self.cols_table.setRowCount(0)
        for spec in specs:
            self._add_column_row(spec)

    def _on_template_selected(self) -> None:
        if not self.is_new:
            return
        code = self.template_combo.currentData()
        tmpl = next((t for t in self.templates if t.code == code), None)
        if tmpl:
            self._apply_specs(tmpl.columns)
            if not self.name_input.text().strip():
                self.name_input.setText(self.ctx.tables.unique_name(tmpl.title))

    def _add_empty_column(self) -> None:
        spec = ColumnSpec(name=f"Столбец {self.cols_table.rowCount() + 1}", type="text")
        self._add_column_row(spec)

    def _add_column_row(self, spec: ColumnSpec) -> None:
        r = self.cols_table.rowCount()
        self.cols_table.insertRow(r)
        self.cols_table.setRowHeight(r, 36)

        # 0. Имя столбца
        name_item = QTableWidgetItem(spec.name)
        name_item.setData(Qt.ItemDataRole.UserRole, spec.id)
        self.cols_table.setItem(r, 0, name_item)

        # 1. Тип данных (Combo)
        type_combo = QComboBox()
        for k, info in T.TYPES.items():
            type_combo.addItem(info.label, k)
        idx = type_combo.findData(spec.type)
        if idx >= 0:
            type_combo.setCurrentIndex(idx)
        self.cols_table.setCellWidget(r, 1, type_combo)

        # 2. Обязательное (CheckBox)
        req_check = QCheckBox()
        req_check.setChecked(spec.required)
        req_widget = QWidget()
        req_widget.setProperty("class", "CellContainer")
        req_l = QHBoxLayout(req_widget)
        req_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        req_l.setContentsMargins(0, 0, 0, 0)
        req_l.addWidget(req_check)
        self.cols_table.setCellWidget(r, 2, req_widget)

        # 3. Значение по умолчанию
        def_item = QTableWidgetItem(spec.default or "")
        def_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cols_table.setItem(r, 3, def_item)

        # 4. Индекс (CheckBox)
        idx_check = QCheckBox()
        idx_check.setChecked(spec.indexed)
        idx_widget = QWidget()
        idx_widget.setProperty("class", "CellContainer")
        idx_l = QHBoxLayout(idx_widget)
        idx_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        idx_l.setContentsMargins(0, 0, 0, 0)
        idx_l.addWidget(idx_check)
        self.cols_table.setCellWidget(r, 4, idx_widget)

    def _delete_column(self) -> None:
        r = self.cols_table.currentRow()
        if r < 0:
            show_warning(self, "Внимание", "Выберите столбец для удаления.")
            return
        if self.cols_table.rowCount() <= 1:
            show_warning(self, "Внимание", "В таблице должен быть хотя бы один столбец.")
            return
        self.cols_table.removeRow(r)

    def _move_column(self, offset: int) -> None:
        curr = self.cols_table.currentRow()
        target = curr + offset
        if curr < 0 or target < 0 or target >= self.cols_table.rowCount():
            return
        specs = self._collect_specs()
        specs[curr], specs[target] = specs[target], specs[curr]
        self._apply_specs(specs)
        self.cols_table.selectRow(target)

    def _collect_specs(self) -> list[ColumnSpec]:
        specs: list[ColumnSpec] = []
        for r in range(self.cols_table.rowCount()):
            name_item = self.cols_table.item(r, 0)
            col_id = name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
            name = name_item.text().strip() if name_item else ""

            type_combo = self.cols_table.cellWidget(r, 1)
            col_type = type_combo.currentData() if type_combo else "text"

            req_widget = self.cols_table.cellWidget(r, 2)
            req_check = req_widget.findChild(QCheckBox) if req_widget else None
            required = req_check.isChecked() if req_check else False

            def_item = self.cols_table.item(r, 3)
            default_val = def_item.text().strip() if def_item else ""
            if not default_val:
                default_val = None

            idx_widget = self.cols_table.cellWidget(r, 4)
            idx_check = idx_widget.findChild(QCheckBox) if idx_widget else None
            indexed = idx_check.isChecked() if idx_check else False

            options = {}
            if col_type == T.CHOICE:
                if self.is_warehouse_mode and name.lower() == "тип операции":
                    options = {"choices": ["Привёз", "Забрал"]}
                else:
                    options = {"choices": []}

            specs.append(
                ColumnSpec(
                    id=col_id,
                    name=name,
                    type=col_type,
                    required=required,
                    default=default_val,
                    indexed=indexed,
                    options=options,
                )
            )
        return specs

    def _on_save(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            show_error(self, "Ошибка", "Укажите название таблицы.")
            return

        specs = self._collect_specs()
        cat_id = self.category_combo.currentData()

        try:
            if self.is_new:
                kind = "warehouse" if self.is_warehouse_mode else "generic"
                self.created_table_id = self.ctx.tables.create(
                    name=name,
                    specs=specs,
                    kind=kind,
                    category_id=cat_id,
                )
            else:
                assert self.table_id is not None
                curr_table = self.ctx.tables.get(self.table_id)
                if curr_table.name != name:
                    self.ctx.tables.rename(self.table_id, name)
                if curr_table.category_id != cat_id:
                    self.ctx.tables.set_category(self.table_id, cat_id)
                self.ctx.tables.update_structure(self.table_id, specs)
                self.created_table_id = self.table_id
            self.accept()
        except WMError as exc:
            show_error(self, "Ошибка сохранения таблицы", str(exc))
