"""Диалог входа в систему."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from wm.core.errors import WMError
from wm.ui.common import show_error

if TYPE_CHECKING:
    from wm.app_context import AppContext


class LoginDialog(QDialog):
    def __init__(self, ctx: "AppContext", parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Вход в систему — Warehouse Manager")
        self.setFixedSize(400, 260)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        header = QLabel("📦 Warehouse Manager")
        header.setProperty("class", "PageTitle")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        sub = QLabel("Введите учётные данные для входа")
        sub.setProperty("class", "PageSubtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.username_input = QLineEdit()
        self.username_input.setMinimumHeight(32)
        self.username_input.setPlaceholderText("Имя пользователя (например, admin)")
        self.password_input = QLineEdit()
        self.password_input.setMinimumHeight(32)
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Пароль")
        self.password_input.returnPressed.connect(self._do_login)

        form.addRow("Логин:", self.username_input)
        form.addRow("Пароль:", self.password_input)
        layout.addLayout(form)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.login_btn = QPushButton("Войти в систему")
        self.login_btn.setProperty("class", "Primary")
        self.login_btn.setMinimumHeight(36)
        self.login_btn.setMinimumWidth(160)
        self.login_btn.clicked.connect(self._do_login)
        btn_layout.addWidget(self.login_btn)

        layout.addLayout(btn_layout)

    def _do_login(self) -> None:
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not username:
            show_error(self, "Ошибка", "Введите имя пользователя.")
            return

        try:
            user = self.ctx.users.authenticate(username, password)
            self.ctx.session.login(user)
            self.accept()
        except WMError as exc:
            show_error(self, "Ошибка входа", str(exc))
