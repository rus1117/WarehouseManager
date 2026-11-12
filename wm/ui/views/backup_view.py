"""Раздел «Резервные копии» и целостность базы данных."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
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

from wm.core.errors import WMError
from wm.services.backup import BackupInfo
from wm.ui.common import ProgressDialog, confirm_dialog, show_error, show_info, show_warning

if TYPE_CHECKING:
    from wm.app_context import AppContext


class BackupView(QWidget):
    def __init__(self, ctx: "AppContext", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PageView")
        self.ctx = ctx

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        header = QLabel("Резервное копирование и безопасность")
        header.setProperty("class", "PageTitle")
        layout.addWidget(header)

        # Верхняя панель быстрых действий
        action_box = QGroupBox("Создание резервной копии")
        action_layout = QHBoxLayout(action_box)

        self.note_input = QLineEdit()
        self.note_input.setMinimumHeight(32)
        self.note_input.setPlaceholderText("Примечание (например, перед обновлением цен)...")
        action_layout.addWidget(self.note_input, stretch=1)

        create_btn = QPushButton("💾 Создать резервную копию")
        create_btn.setProperty("class", "Primary")
        create_btn.setMinimumHeight(32)
        create_btn.clicked.connect(self._create_backup)
        action_layout.addWidget(create_btn)

        check_btn = QPushButton("🔍 Проверить целостность базы")
        check_btn.setMinimumHeight(32)
        check_btn.clicked.connect(self._check_integrity)
        action_layout.addWidget(check_btn)

        layout.addWidget(action_box)

        # Таблица списка резервных копий
        list_header = QLabel("Существующие резервные копии:")
        list_header.setProperty("class", "SectionTitle")
        layout.addWidget(list_header)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Имя файла", "Дата создания", "Размер", "Путь"])
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.verticalHeader().setMinimumWidth(34)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(0, 260)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(1, 150)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(2, 100)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, stretch=1)

        # Нижняя панель действий
        bottom_bar = QHBoxLayout()

        restore_btn = QPushButton("🔄 Восстановить из выбранной копии")
        restore_btn.setProperty("class", "Danger")
        restore_btn.clicked.connect(self._restore_backup)
        bottom_bar.addWidget(restore_btn)

        restore_external_btn = QPushButton("📂 Восстановить из внешнего файла...")
        restore_external_btn.clicked.connect(self._restore_from_file)
        bottom_bar.addWidget(restore_external_btn)

        bottom_bar.addStretch()

        refresh_btn = QPushButton("🔄 Обновить список")
        refresh_btn.clicked.connect(self.refresh)
        bottom_bar.addWidget(refresh_btn)

        layout.addLayout(bottom_bar)
        self.refresh()

    def refresh(self) -> None:
        try:
            backups = self.ctx.backup.list_backups()
            self.table.setRowCount(len(backups))
            for r, b in enumerate(backups):
                self.table.setItem(r, 0, QTableWidgetItem(b.filename))
                dt_item = QTableWidgetItem(b.created_at.strftime("%d.%m.%Y %H:%M:%S"))
                dt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, 1, dt_item)
                size_kb = b.size_bytes / 1024.0
                size_str = f"{size_kb / 1024:.2f} МБ" if size_kb > 1024 else f"{size_kb:.1f} КБ"
                sz_item = QTableWidgetItem(size_str)
                sz_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, 2, sz_item)
                self.table.setItem(r, 3, QTableWidgetItem(str(b.path)))
                self.table.item(r, 0).setData(Qt.ItemDataRole.UserRole, b)
        except Exception as exc:
            show_error(self, "Ошибка загрузки списка резервных копий", str(exc))

    def _selected_backup(self) -> BackupInfo | None:
        r = self.table.currentRow()
        if r < 0:
            return None
        return self.table.item(r, 0).data(Qt.ItemDataRole.UserRole)

    def _create_backup(self) -> None:
        note = self.note_input.text().strip()
        progress_dlg = ProgressDialog("Резервное копирование", "Создание копии...", self)
        progress_dlg.show()
        try:
            dest = self.ctx.backup.create_backup(progress=progress_dlg.update_progress, note=note)
            progress_dlg.close()
            self.note_input.clear()
            self.refresh()
            show_info(self, "Успех", f"Резервная копия успешно создана:\n{dest.name}")
        except WMError as exc:
            progress_dlg.close()
            show_error(self, "Ошибка резервного копирования", str(exc))

    def _restore_backup(self) -> None:
        b = self._selected_backup()
        if not b:
            show_warning(self, "Внимание", "Выберите резервную копию из списка.")
            return

        if not confirm_dialog(
            self,
            "ВНИМАНИЕ: Восстановление данных",
            f"Текущие данные будут заменены состоянием из копии:\n«{b.filename}» ({b.created_at.strftime('%d.%m.%Y %H:%M')}).\n"
            "Перед заменой будет автоматически создана страховочная копия текущей базы.\n\nПродолжить?",
        ):
            return

        progress_dlg = ProgressDialog("Восстановление базы", "Восстановление...", self)
        progress_dlg.show()
        try:
            self.ctx.backup.restore_backup(b.path, progress=progress_dlg.update_progress)
            progress_dlg.close()
            self.refresh()
            show_info(self, "Успех", "База данных успешно восстановлена.")
        except WMError as exc:
            progress_dlg.close()
            show_error(self, "Ошибка восстановления", str(exc))

    def _restore_from_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Выберите файл базы для восстановления", "", "SQLite DB (*.db)")
        if not path:
            return
        if not confirm_dialog(
            self,
            "Подтверждение",
            f"Восстановить базу данных из файла:\n{path}?\nТекущие данные будут заменены.",
        ):
            return
        progress_dlg = ProgressDialog("Восстановление базы", "Восстановление...", self)
        progress_dlg.show()
        try:
            self.ctx.backup.restore_backup(path, progress=progress_dlg.update_progress)
            progress_dlg.close()
            self.refresh()
            show_info(self, "Успех", "База данных успешно восстановлена из внешнего файла.")
        except WMError as exc:
            progress_dlg.close()
            show_error(self, "Ошибка восстановления", str(exc))

    def _check_integrity(self) -> None:
        problems = self.ctx.backup.check_integrity()
        if not problems:
            show_info(self, "Проверка целостности", "Проверка завершена успешно! Ошибок и повреждений в базе данных не обнаружено.")
        else:
            msg = "Обнаружены следующие проблемы:\n" + "\n".join(problems[:10])
            show_error(self, "Проверка целостности", msg)
