"""Раздел «Импорт данных» из Excel (XLSX, XLSM) и CSV."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from wm.core import types as T
from wm.core.errors import OperationCancelled, WMError
from wm.services.common import ColumnSpec
from wm.services.importer import (
    DUP_ALL,
    DUP_SKIP,
    DUP_WARN,
    FileInfo,
    ImportColumn,
    ImportPlan,
    suggest_columns,
)
from wm.ui.common import ProgressDialog, show_error, show_info, show_warning

if TYPE_CHECKING:
    from wm.app_context import AppContext


class ImportView(QWidget):
    def __init__(
        self,
        ctx: "AppContext",
        on_table_imported: Callable[[int], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PageView")
        self.ctx = ctx
        self.on_table_imported = on_table_imported
        self.file_info: FileInfo | None = None
        self.preview_headers: list[str] = []
        self.preview_rows: list[list] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        header = QLabel("Импорт данных из Excel и CSV")
        header.setProperty("class", "PageTitle")
        layout.addWidget(header)

        # Шаг 1: Выбор файла
        file_box = QGroupBox("1. Выбор файла (XLSX, XLSM, CSV)")
        file_layout = QHBoxLayout(file_box)
        self.file_path_input = QLineEdit()
        self.file_path_input.setReadOnly(True)
        self.file_path_input.setPlaceholderText("Нажмите «Обзор...» для выбора файла")
        file_layout.addWidget(self.file_path_input, stretch=1)

        browse_btn = QPushButton("📂 Обзор...")
        browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(browse_btn)

        file_layout.addWidget(QLabel("Лист:"))
        self.sheet_combo = QComboBox()
        self.sheet_combo.setMinimumWidth(180)
        self.sheet_combo.currentIndexChanged.connect(self._on_sheet_changed)
        file_layout.addWidget(self.sheet_combo)

        layout.addWidget(file_box)

        # Шаг 2: Назначение импорта (Новая таблица / Существующая)
        dest_box = QGroupBox("2. Назначение импорта")
        dest_layout = QHBoxLayout(dest_box)

        self.mode_new_radio = QRadioButton("Создать новую таблицу:")
        self.mode_new_radio.setChecked(True)
        self.mode_new_radio.toggled.connect(self._on_mode_toggled)
        dest_layout.addWidget(self.mode_new_radio)

        self.new_table_name_input = QLineEdit()
        self.new_table_name_input.setPlaceholderText("Название новой таблицы")
        dest_layout.addWidget(self.new_table_name_input, stretch=1)

        dest_layout.addSpacing(12)

        self.mode_exist_radio = QRadioButton("Добавить в существующую:")
        dest_layout.addWidget(self.mode_exist_radio)

        self.exist_table_combo = QComboBox()
        self.exist_table_combo.setEnabled(False)
        self.exist_table_combo.setMinimumWidth(200)
        self.exist_table_combo.currentIndexChanged.connect(self._on_exist_table_changed)
        dest_layout.addWidget(self.exist_table_combo, stretch=1)

        layout.addWidget(dest_box)

        # Шаг 3: Сопоставление столбцов
        mapping_box = QGroupBox("3. Сопоставление столбцов и предпросмотр")
        mapping_layout = QVBoxLayout(mapping_box)

        self.mapping_table = QTableWidget()
        self.mapping_table.setColumnCount(4)
        self.mapping_table.setHorizontalHeaderLabels([
            "Столбец в файле", "Пример данных", "Столбец назначения / Имя", "Тип данных"
        ])
        self.mapping_table.setAlternatingRowColors(True)
        self.mapping_table.verticalHeader().setDefaultSectionSize(36)
        self.mapping_table.verticalHeader().setMinimumWidth(34)
        hh = self.mapping_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(0, 180)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(2, 220)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(3, 175)
        mapping_layout.addWidget(self.mapping_table)

        layout.addWidget(mapping_box, stretch=1)

        # Шаг 4: Опции дубликатов и ошибок
        opt_box = QGroupBox("4. Обработка дубликатов")
        opt_layout = QHBoxLayout(opt_box)

        self.dup_all_radio = QRadioButton("Импортировать все строки")
        self.dup_all_radio.setChecked(True)
        self.dup_skip_radio = QRadioButton("Пропускать точные дубликаты")
        self.dup_warn_radio = QRadioButton("Предупреждать о дубликатах")

        opt_layout.addWidget(self.dup_all_radio)
        opt_layout.addWidget(self.dup_skip_radio)
        opt_layout.addWidget(self.dup_warn_radio)
        opt_layout.addStretch()

        layout.addWidget(opt_box)

        # Кнопка выполнения импорта
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()

        self.import_btn = QPushButton("📥  Начать импорт")
        self.import_btn.setProperty("class", "Primary")
        self.import_btn.setMinimumHeight(38)
        self.import_btn.setMinimumWidth(180)
        self.import_btn.setEnabled(False)
        self.import_btn.clicked.connect(self._do_import)
        bottom_bar.addWidget(self.import_btn)

        layout.addLayout(bottom_bar)

    def refresh(self) -> None:
        self.exist_table_combo.clear()
        for t in self.ctx.tables.list():
            self.exist_table_combo.addItem(t.name, t.id)

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите файл для импорта", "", "Таблицы (*.xlsx *.xlsm *.csv);;Excel (*.xlsx *.xlsm);;CSV (*.csv)"
        )
        if not path:
            return

        self.file_path_input.setText(path)
        try:
            self.file_info = self.ctx.importer.analyze(path)
            self.sheet_combo.clear()
            for s in self.file_info.sheets:
                self.sheet_combo.addItem(f"{s.name} ({s.rows} строк)", s.name)
            self.new_table_name_input.setText(self.ctx.tables.unique_name(Path(path).stem))
            self._load_preview()
            self.import_btn.setEnabled(True)
        except WMError as exc:
            show_error(self, "Ошибка анализа файла", str(exc))

    def _on_sheet_changed(self) -> None:
        if self.file_info:
            self._load_preview()

    def _on_mode_toggled(self) -> None:
        is_new = self.mode_new_radio.isChecked()
        self.new_table_name_input.setEnabled(is_new)
        self.exist_table_combo.setEnabled(not is_new)
        self._load_preview()

    def _on_exist_table_changed(self) -> None:
        if not self.mode_new_radio.isChecked():
            self._load_preview()

    def _load_preview(self) -> None:
        if not self.file_info or self.sheet_combo.currentIndex() < 0:
            return
        sheet_name = self.sheet_combo.currentData()
        self.preview_headers, self.preview_rows = self.ctx.importer.preview(
            self.file_info, sheet_name, header_row=1, limit=50
        )

        target_table = None
        if not self.mode_new_radio.isChecked():
            tid = self.exist_table_combo.currentData()
            if tid:
                target_table = self.ctx.tables.get(tid)

        suggested = suggest_columns(self.preview_headers, self.preview_rows, target_table)

        self.mapping_table.setRowCount(len(suggested))
        for r, col in enumerate(suggested):
            self.mapping_table.setRowHeight(r, 36)
            # 0. Исходный столбец
            self.mapping_table.setItem(r, 0, QTableWidgetItem(col.source_name))

            # 1. Пример данных
            sample = ""
            for row in self.preview_rows:
                if col.source_index < len(row) and row[col.source_index] is not None:
                    sample = str(row[col.source_index])
                    break
            self.mapping_table.setItem(r, 1, QTableWidgetItem(sample[:60]))

            # 2. Назначение
            if target_table:
                cb = QComboBox()
                cb.addItem("— Пропустить —", None)
                for tcol in target_table.columns:
                    cb.addItem(tcol.name, tcol.id)
                if col.target_col_id:
                    idx = cb.findData(col.target_col_id)
                    if idx >= 0:
                        cb.setCurrentIndex(idx)
                self.mapping_table.setCellWidget(r, 2, cb)
                self.mapping_table.setItem(r, 3, QTableWidgetItem("По таблице"))
            else:
                le = QLineEdit(col.new_spec.name if col.new_spec else col.source_name)
                self.mapping_table.setCellWidget(r, 2, le)

                tcb = QComboBox()
                for k, info in T.TYPES.items():
                    tcb.addItem(info.label, k)
                cur_type = col.new_spec.type if col.new_spec else "text"
                t_idx = tcb.findData(cur_type)
                if t_idx >= 0:
                    tcb.setCurrentIndex(t_idx)
                self.mapping_table.setCellWidget(r, 3, tcb)

    def _do_import(self) -> None:
        if not self.file_info:
            return

        sheet_name = self.sheet_combo.currentData()
        is_new = self.mode_new_radio.isChecked()

        columns: list[ImportColumn] = []
        for r in range(self.mapping_table.rowCount()):
            src_name = self.mapping_table.item(r, 0).text()
            if is_new:
                target_name = self.mapping_table.cellWidget(r, 2).text().strip()
                target_type = self.mapping_table.cellWidget(r, 3).currentData()
                spec = ColumnSpec(name=target_name, type=target_type)
                columns.append(ImportColumn(source_index=r, source_name=src_name, new_spec=spec))
            else:
                target_col_id = self.mapping_table.cellWidget(r, 2).currentData()
                skip = target_col_id is None
                columns.append(ImportColumn(source_index=r, source_name=src_name, target_col_id=target_col_id, skip=skip))

        dup_mode = DUP_ALL
        if self.dup_skip_radio.isChecked():
            dup_mode = DUP_SKIP
        elif self.dup_warn_radio.isChecked():
            dup_mode = DUP_WARN

        target_table_id = None if is_new else self.exist_table_combo.currentData()
        new_name = self.new_table_name_input.text().strip() if is_new else ""

        plan = ImportPlan(
            path=self.file_info.path,
            sheet=sheet_name,
            header_row=1,
            columns=columns,
            target_table_id=target_table_id,
            new_table_name=new_name,
            duplicate_mode=dup_mode,
        )

        progress_dlg = ProgressDialog("Импорт данных", "Подготовка...", self)
        progress_dlg.show()

        try:
            res = self.ctx.importer.run(
                plan=plan,
                progress=progress_dlg.update_progress,
                cancelled=lambda: progress_dlg.is_cancelled,
                dry_run=False,
            )
            progress_dlg.close()
            msg = f"Успешно импортировано строк: {res.imported}."
            if res.skipped_duplicates:
                msg += f"\nПропущено дубликатов: {res.skipped_duplicates}."
            if res.error_rows:
                msg += f"\nСтрок с ошибками/пропущено: {res.error_rows}."
            show_info(self, "Импорт завершён", msg)
            if res.table_id:
                self.on_table_imported(res.table_id)
        except OperationCancelled:
            progress_dlg.close()
            show_warning(self, "Отмена", "Импорт отменён пользователем. Данные не были сохранены.")
        except WMError as exc:
            progress_dlg.close()
            show_error(self, "Ошибка импорта", str(exc))
