"""Встроенный экран (раздел) конструктора новой таблицы."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
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
from wm.services.templates import get_templates
from wm.ui.common import show_error, show_warning

if TYPE_CHECKING:
    from wm.app_context import AppContext


class CreateTableView(QWidget):
    def __init__(
        self,
        ctx: "AppContext",
        on_table_created: Callable[[int], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PageView")
        self.ctx = ctx
        self.on_table_created = on_table_created
        self.templates = get_templates()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Заголовок
        header_box = QVBoxLayout()
        header_box.setSpacing(2)
        header = QLabel("Конструктор создания таблицы")
        header.setProperty("class", "PageTitle")
        header_box.addWidget(header)

        sub = QLabel("Настройте структуру столбцов или выберите готовый отраслевой шаблон:")
        sub.setProperty("class", "PageSubtitle")
        header_box.addWidget(sub)
        layout.addLayout(header_box)

        # 1. Параметры таблицы
        top_box = QGroupBox("Параметры таблицы")
        top_form = QFormLayout(top_box)
        top_form.setSpacing(8)
        top_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Например: Складской учёт (Ноябрь 2026)")
        self.name_input.setMinimumHeight(30)
        top_form.addRow("Название таблицы*:", self.name_input)

        self.category_combo = QComboBox()
        self.category_combo.setMinimumHeight(30)
        top_form.addRow("Категория / Папка:", self.category_combo)

        self.template_combo = QComboBox()
        self.template_combo.setMinimumHeight(30)
        for tmpl in self.templates:
            self.template_combo.addItem(f"📋 {tmpl.title}", tmpl.code)
        self.template_combo.currentIndexChanged.connect(self._on_template_selected)
        top_form.addRow("Готовый шаблон:", self.template_combo)

        layout.addWidget(top_box)

        # 2. Столбцы таблицы (растягиваются на всё свободное место)
        cols_box = QGroupBox("Столбцы таблицы")
        cols_layout = QVBoxLayout(cols_box)
        cols_layout.setSpacing(8)

        col_tools = QHBoxLayout()
        add_col_btn = QPushButton("＋ Добавить столбец")
        add_col_btn.clicked.connect(self._add_empty_column)
        col_tools.addWidget(add_col_btn)

        del_col_btn = QPushButton("🗑️ Удалить столбец")
        del_col_btn.clicked.connect(self._delete_column)
        col_tools.addWidget(del_col_btn)

        col_tools.addSpacing(8)

        up_col_btn = QPushButton("▲ Вверх")
        up_col_btn.clicked.connect(lambda: self._move_column(-1))
        col_tools.addWidget(up_col_btn)

        down_col_btn = QPushButton("▼ Вниз")
        down_col_btn.clicked.connect(lambda: self._move_column(1))
        col_tools.addWidget(down_col_btn)

        col_tools.addStretch()

        reset_btn = QPushButton("🔄 Сбросить к шаблону")
        reset_btn.clicked.connect(self._on_template_selected)
        col_tools.addWidget(reset_btn)

        cols_layout.addLayout(col_tools)

        self.cols_table = QTableWidget()
        self.cols_table.setColumnCount(5)
        self.cols_table.setHorizontalHeaderLabels([
            "Имя столбца", "Тип данных", "Обязательное", "По умолчанию", "Быстрый поиск"
        ])
        self.cols_table.setAlternatingRowColors(True)
        self.cols_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cols_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.cols_table.verticalHeader().setDefaultSectionSize(36)
        self.cols_table.verticalHeader().setMinimumWidth(34)

        # Настройка пропорций и ширин колонок
        h_header = self.cols_table.horizontalHeader()
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Имя столбца растягивается
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)    # Тип данных
        h_header.resizeSection(1, 175)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)    # Обязательное
        h_header.resizeSection(2, 120)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)    # По умолчанию
        h_header.resizeSection(3, 145)
        h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)    # Быстрый поиск
        h_header.resizeSection(4, 135)

        cols_layout.addWidget(self.cols_table, stretch=1)
        layout.addWidget(cols_box, stretch=1)

        # 3. Нижняя панель действий (всегда закреплена внизу)
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()

        create_btn = QPushButton("✓  Создать и открыть таблицу")
        create_btn.setProperty("class", "Primary")
        create_btn.setMinimumHeight(38)
        create_btn.setMinimumWidth(240)
        create_btn.clicked.connect(self._create_table)
        bottom_bar.addWidget(create_btn)

        layout.addLayout(bottom_bar)

        self.refresh()

    def refresh(self) -> None:
        self.category_combo.clear()
        self.category_combo.addItem("— Без категории —", None)
        for cid, cname in self.ctx.tables.categories():
            self.category_combo.addItem(cname, cid)
        cur_name = self.name_input.text().strip()
        if not cur_name or self.ctx.tables.name_exists(cur_name):
            self._on_template_selected()

    def select_warehouse_template(self) -> None:
        idx = self.template_combo.findData("warehouse")
        if idx >= 0:
            self.template_combo.setCurrentIndex(idx)
        self._on_template_selected()

    def _on_template_selected(self) -> None:
        code = self.template_combo.currentData()
        tmpl = next((t for t in self.templates if t.code == code), None)
        if tmpl:
            self._apply_specs(tmpl.columns)
            self.name_input.setText(self.ctx.tables.unique_name(tmpl.title))

    def _apply_specs(self, specs: list[ColumnSpec]) -> None:
        self.cols_table.setRowCount(0)
        for spec in specs:
            self._add_column_row(spec)

    def _add_empty_column(self) -> None:
        spec = ColumnSpec(name=f"Столбец {self.cols_table.rowCount() + 1}", type="text")
        self._add_column_row(spec)
        self.cols_table.selectRow(self.cols_table.rowCount() - 1)

    def _add_column_row(self, spec: ColumnSpec) -> None:
        r = self.cols_table.rowCount()
        self.cols_table.insertRow(r)
        self.cols_table.setRowHeight(r, 36)

        # 0. Имя столбца
        name_item = QTableWidgetItem(spec.name)
        self.cols_table.setItem(r, 0, name_item)

        # 1. Тип данных (выпадающий список с понятными названиями)
        type_combo = QComboBox()
        for k, info in T.TYPES.items():
            type_combo.addItem(info.label, k)
        idx = type_combo.findData(spec.type)
        if idx >= 0:
            type_combo.setCurrentIndex(idx)
        self.cols_table.setCellWidget(r, 1, type_combo)

        # 2. Обязательное (чекбокс по центру)
        req_check = QCheckBox()
        req_check.setChecked(spec.required)
        req_check.setCursor(Qt.CursorShape.PointingHandCursor)
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

        # 4. Индекс (чекбокс по центру)
        idx_check = QCheckBox()
        idx_check.setChecked(spec.indexed)
        idx_check.setCursor(Qt.CursorShape.PointingHandCursor)
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
            show_warning(self, "Внимание", "В таблице должен оставаться хотя бы один столбец.")
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
        is_warehouse = self.template_combo.currentData() == "warehouse"
        for r in range(self.cols_table.rowCount()):
            name_item = self.cols_table.item(r, 0)
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
                if is_warehouse and name.lower() == "тип операции":
                    options = {"choices": ["Привёз", "Забрал"]}
                else:
                    options = {"choices": []}

            if is_warehouse and name.lower() in ("фамилия", "имя", "отчество", "название товара"):
                options["autocomplete"] = True

            specs.append(
                ColumnSpec(
                    name=name,
                    type=col_type,
                    required=required,
                    default=default_val,
                    indexed=indexed,
                    options=options,
                )
            )
        return specs

    def _create_table(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            show_error(self, "Ошибка", "Укажите название таблицы.")
            return

        specs = self._collect_specs()
        cat_id = self.category_combo.currentData()
        kind = "warehouse" if self.template_combo.currentData() == "warehouse" else "generic"

        try:
            new_id = self.ctx.tables.create(
                name=name,
                specs=specs,
                kind=kind,
                category_id=cat_id,
            )
            code = self.template_combo.currentData()
            tmpl = next((t for t in self.templates if t.code == code), None)
            if tmpl:
                self.name_input.setText(self.ctx.tables.unique_name(tmpl.title))
            self.on_table_created(new_id)
        except WMError as exc:
            show_error(self, "Ошибка создания таблицы", str(exc))
