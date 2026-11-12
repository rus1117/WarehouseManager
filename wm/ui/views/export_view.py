"""Раздел «Экспорт данных» в форматы XLSX и CSV."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from wm.core.errors import OperationCancelled, WMError
from wm.services.exporter import ExportSource, safe_filename
from wm.ui.common import ProgressDialog, show_error, show_info, show_warning

if TYPE_CHECKING:
    from wm.app_context import AppContext


class ExportView(QWidget):
    def __init__(self, ctx: "AppContext", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PageView")
        self.ctx = ctx

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        header = QLabel("Экспорт таблиц")
        header.setProperty("class", "PageTitle")
        layout.addWidget(header)

        # Выбор таблицы для экспорта
        table_box = QGroupBox("1. Выберите таблицу для экспорта")
        table_layout = QVBoxLayout(table_box)
        table_layout.setSpacing(8)

        self.table_combo = QComboBox()
        self.table_combo.setMinimumHeight(32)
        self.table_combo.currentIndexChanged.connect(self._on_table_changed)
        table_layout.addWidget(self.table_combo)

        self.info_label = QLabel()
        self.info_label.setProperty("class", "PageSubtitle")
        table_layout.addWidget(self.info_label)

        layout.addWidget(table_box)

        # Формат экспорта
        fmt_box = QGroupBox("2. Формат файла")
        fmt_layout = QVBoxLayout(fmt_box)
        fmt_layout.setSpacing(8)

        self.fmt_xlsx_radio = QRadioButton("Книга Excel (*.xlsx) — с форматированием дат, сумм и автошириной")
        self.fmt_xlsx_radio.setChecked(True)
        self.fmt_xlsx_radio.toggled.connect(self._on_format_changed)
        self.fmt_csv_radio = QRadioButton("Текстовый CSV (*.csv) — универсальный формат с разделителем")

        fmt_layout.addWidget(self.fmt_xlsx_radio)
        fmt_layout.addWidget(self.fmt_csv_radio)

        layout.addWidget(fmt_box)

        # Путь сохранения
        path_box = QGroupBox("3. Место сохранения файла")
        path_layout = QHBoxLayout(path_box)

        self.dest_path_input = QLineEdit()
        self.dest_path_input.setMinimumHeight(32)
        self.dest_path_input.setPlaceholderText("Выберите путь для сохранения...")
        path_layout.addWidget(self.dest_path_input, stretch=1)

        browse_btn = QPushButton("📂 Обзор...")
        browse_btn.setMinimumHeight(32)
        browse_btn.clicked.connect(self._browse_save_path)
        path_layout.addWidget(browse_btn)

        layout.addWidget(path_box)

        # Кнопка экспорта
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()

        self.export_btn = QPushButton("📤  Экспортировать")
        self.export_btn.setProperty("class", "Primary")
        self.export_btn.setMinimumHeight(38)
        self.export_btn.setMinimumWidth(180)
        self.export_btn.clicked.connect(self._do_export)
        bottom_bar.addWidget(self.export_btn)

        layout.addLayout(bottom_bar)
        layout.addStretch()

    def refresh(self) -> None:
        self.table_combo.clear()
        tables = self.ctx.tables.list(with_counts=True)
        for t in tables:
            self.table_combo.addItem(f"{t.name} ({t.row_count or 0} записей)", t.id)
        self._on_table_changed()

    def _on_format_changed(self) -> None:
        cur = self.dest_path_input.text().strip()
        if cur:
            p = Path(cur)
            ext = ".xlsx" if self.fmt_xlsx_radio.isChecked() else ".csv"
            self.dest_path_input.setText(str(p.with_suffix(ext)))

    def _on_table_changed(self) -> None:
        tid = self.table_combo.currentData()
        if not tid:
            self.info_label.setText("Нет доступных таблиц.")
            self.export_btn.setEnabled(False)
            return

        table = self.ctx.tables.get(tid, with_count=True)
        self.info_label.setText(
            f"Столбцов: {len(table.columns)}  |  Всего записей: {table.row_count or 0}  |  Категория: {table.category or '—'}"
        )
        self.export_btn.setEnabled(True)

        ext = ".xlsx" if self.fmt_xlsx_radio.isChecked() else ".csv"
        default_name = f"{safe_filename(table.name)}{ext}"
        default_dir = Path.home() / "Documents"
        if not default_dir.exists():
            default_dir = Path.home()
        self.dest_path_input.setText(str(default_dir / default_name))

    def _browse_save_path(self) -> None:
        ext = "xlsx" if self.fmt_xlsx_radio.isChecked() else "csv"
        filter_str = "Excel (*.xlsx)" if ext == "xlsx" else "CSV (*.csv)"
        current = self.dest_path_input.text()
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить файл", current, filter_str)
        if path:
            self.dest_path_input.setText(path)

    def _do_export(self) -> None:
        tid = self.table_combo.currentData()
        dest = self.dest_path_input.text().strip()
        if not tid or not dest:
            show_warning(self, "Внимание", "Укажите таблицу и путь сохранения.")
            return

        table = self.ctx.tables.get(tid)
        fmt = "xlsx" if self.fmt_xlsx_radio.isChecked() else "csv"

        progress_dlg = ProgressDialog("Экспорт данных", "Экспорт строк...", self)
        progress_dlg.show()

        try:
            out_files = self.ctx.exporter.export(
                sources=[ExportSource(table=table)],
                path=dest,
                fmt=fmt,
                progress=progress_dlg.update_progress,
                cancelled=lambda: progress_dlg.is_cancelled,
            )
            progress_dlg.close()
            show_info(self, "Успех", f"Данные успешно экспортированы в файл:\n{out_files[0]}")
        except OperationCancelled:
            progress_dlg.close()
            show_warning(self, "Отмена", "Экспорт отменён.")
        except WMError as exc:
            progress_dlg.close()
            show_error(self, "Ошибка экспорта", str(exc))
