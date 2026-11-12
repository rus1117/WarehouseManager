"""Раздел «Настройки» приложения."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from wm import __version__
from wm.core.paths import db_path, is_portable
from wm.core.security import ROLE_ADMIN
from wm.ui.common import show_info
from wm.ui.dialogs.user_management_dialog import UserManagementDialog

if TYPE_CHECKING:
    from wm.app_context import AppContext


class SettingsView(QWidget):
    def __init__(
        self,
        ctx: "AppContext",
        on_theme_changed: Callable[[str], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PageView")
        self.ctx = ctx
        self.on_theme_changed = on_theme_changed

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        header = QLabel("Настройки системы")
        header.setProperty("class", "PageTitle")
        layout.addWidget(header)

        # Внешний вид
        ui_box = QGroupBox("Внешний вид и интерфейс")
        ui_layout = QFormLayout(ui_box)
        ui_layout.setSpacing(10)
        ui_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.theme_combo = QComboBox()
        self.theme_combo.setMinimumHeight(32)
        self.theme_combo.addItem("☀️ Светлая тема", "light")
        self.theme_combo.addItem("🌙 Тёмная тема", "dark")
        self.theme_combo.currentIndexChanged.connect(self._on_theme_selected)
        ui_layout.addRow("Тема оформления:", self.theme_combo)

        self.page_size_spin = QSpinBox()
        self.page_size_spin.setMinimumHeight(32)
        self.page_size_spin.setRange(50, 2000)
        self.page_size_spin.setSingleStep(50)
        ui_layout.addRow("Строк на страницу в таблицах:", self.page_size_spin)

        layout.addWidget(ui_box)

        # Резервное копирование
        backup_box = QGroupBox("Параметры резервного копирования")
        backup_layout = QFormLayout(backup_box)
        backup_layout.setSpacing(10)
        backup_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.backup_keep_spin = QSpinBox()
        self.backup_keep_spin.setMinimumHeight(32)
        self.backup_keep_spin.setRange(1, 100)
        backup_layout.addRow("Хранить последних копий:", self.backup_keep_spin)

        path_row = QHBoxLayout()
        self.backup_dir_input = QLineEdit()
        self.backup_dir_input.setMinimumHeight(32)
        self.backup_dir_input.setPlaceholderText("По умолчанию (папка программы)")
        path_row.addWidget(self.backup_dir_input, stretch=1)
        browse_b_btn = QPushButton("📂 Обзор...")
        browse_b_btn.setMinimumHeight(32)
        browse_b_btn.clicked.connect(self._browse_backup_dir)
        path_row.addWidget(browse_b_btn)

        backup_layout.addRow("Папка резервных копий:", path_row)
        layout.addWidget(backup_box)

        # Пользователи и безопасность
        sec_box = QGroupBox("Пользователи и безопасность")
        sec_layout = QHBoxLayout(sec_box)

        self.manage_users_btn = QPushButton("👥  Управление пользователями и ролями")
        self.manage_users_btn.setMinimumHeight(36)
        self.manage_users_btn.clicked.connect(self._open_user_management)
        sec_layout.addWidget(self.manage_users_btn)
        sec_layout.addStretch()
        layout.addWidget(sec_box)

        # О программе
        info_box = QGroupBox("О программе")
        info_layout = QFormLayout(info_box)
        info_layout.setSpacing(8)
        info_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        info_layout.addRow("Версия:", QLabel(f"Warehouse Manager v{__version__}"))
        mode_str = "Портативная (Portable) — база рядом с программой" if is_portable() else "Установленная в систему"
        info_layout.addRow("Режим работы:", QLabel(mode_str))
        info_layout.addRow("Файл базы данных:", QLabel(str(db_path())))

        layout.addWidget(info_box)

        # Сохранение настроек
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        save_btn = QPushButton("✓  Сохранить настройки")
        save_btn.setProperty("class", "Primary")
        save_btn.setMinimumHeight(38)
        save_btn.setMinimumWidth(200)
        save_btn.clicked.connect(self._save_settings)
        btn_bar.addWidget(save_btn)

        layout.addLayout(btn_bar)
        layout.addStretch()

    def refresh(self) -> None:
        theme = self.ctx.settings.get("theme", "light")
        idx = self.theme_combo.findData(theme)
        if idx >= 0:
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(idx)
            self.theme_combo.blockSignals(False)

        self.page_size_spin.setValue(int(self.ctx.settings.get("page_size", 200)))
        self.backup_keep_spin.setValue(int(self.ctx.settings.get("backup_keep_count", 10)))
        self.backup_dir_input.setText(self.ctx.settings.get("backup_dir", ""))

        is_admin = self.ctx.session.user and self.ctx.session.user.role == ROLE_ADMIN
        self.manage_users_btn.setEnabled(bool(is_admin))

    def _on_theme_selected(self) -> None:
        theme = self.theme_combo.currentData()
        self.ctx.settings.set("theme", theme)
        self.on_theme_changed(theme)

    def _browse_backup_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Выберите папку для резервных копий")
        if path:
            self.backup_dir_input.setText(path)

    def _save_settings(self) -> None:
        self.ctx.settings.set_many({
            "theme": self.theme_combo.currentData(),
            "page_size": self.page_size_spin.value(),
            "backup_keep_count": self.backup_keep_spin.value(),
            "backup_dir": self.backup_dir_input.text().strip(),
        })
        show_info(self, "Настройки", "Настройки успешно сохранены.")

    def _open_user_management(self) -> None:
        dlg = UserManagementDialog(self.ctx, parent=self)
        dlg.exec()
