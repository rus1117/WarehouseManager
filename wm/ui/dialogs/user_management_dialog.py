"""Диалог управления пользователями системы (для администратора)."""
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
)

from wm.core.errors import WMError
from wm.core.security import ROLE_ADMIN, ROLE_LABELS, ROLE_OPERATOR, ROLE_VIEWER
from wm.ui.common import confirm_dialog, show_error, show_info, show_warning

if TYPE_CHECKING:
    from wm.app_context import AppContext


class UserEditDialog(QDialog):
    def __init__(self, is_new: bool = True, user_data: dict | None = None, parent=None):
        super().__init__(parent)
        self.is_new = is_new
        self.user_data = user_data or {}
        self.setWindowTitle("Новый пользователь" if is_new else "Редактирование пользователя")
        self.setFixedSize(390, 290)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.username_input = QLineEdit()
        self.username_input.setMinimumHeight(30)
        self.username_input.setText(self.user_data.get("username", ""))
        if not is_new:
            self.username_input.setEnabled(False)

        self.full_name_input = QLineEdit()
        self.full_name_input.setMinimumHeight(30)
        self.full_name_input.setText(self.user_data.get("full_name", ""))

        self.role_combo = QComboBox()
        self.role_combo.setMinimumHeight(30)
        self.role_combo.addItem("Администратор", ROLE_ADMIN)
        self.role_combo.addItem("Оператор", ROLE_OPERATOR)
        self.role_combo.addItem("Только просмотр", ROLE_VIEWER)
        curr_role = self.user_data.get("role", ROLE_OPERATOR)
        idx = self.role_combo.findData(curr_role)
        if idx >= 0:
            self.role_combo.setCurrentIndex(idx)

        self.password_input = QLineEdit()
        self.password_input.setMinimumHeight(30)
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        if not is_new:
            self.password_input.setPlaceholderText("Оставьте пустым, если не меняется")

        self.active_check = QCheckBox("Учётная запись активна")
        self.active_check.setChecked(self.user_data.get("is_active", True))

        form.addRow("Логин*:", self.username_input)
        form.addRow("ФИО:", self.full_name_input)
        form.addRow("Роль:", self.role_combo)
        form.addRow("Пароль*:" if is_new else "Пароль:", self.password_input)
        if not is_new:
            form.addRow("", self.active_check)

        layout.addLayout(form)
        layout.addStretch()

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Сохранить")
        save_btn.setProperty("class", "Primary")
        save_btn.clicked.connect(self.accept)

        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(save_btn)
        layout.addLayout(btn_box)

    def get_data(self) -> dict:
        return {
            "username": self.username_input.text().strip(),
            "full_name": self.full_name_input.text().strip(),
            "role": self.role_combo.currentData(),
            "password": self.password_input.text(),
            "is_active": self.active_check.isChecked(),
        }


class UserManagementDialog(QDialog):
    def __init__(self, ctx: "AppContext", parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Управление пользователями")
        self.resize(680, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        header = QLabel("Пользователи системы")
        header.setProperty("class", "PageTitle")
        layout.addWidget(header)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "Логин", "ФИО", "Роль", "Статус"])
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.verticalHeader().setMinimumWidth(34)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(0, 55)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(1, 130)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(3, 150)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(4, 110)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, stretch=1)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("＋ Добавить пользователя")
        add_btn.setProperty("class", "Primary")
        add_btn.clicked.connect(self._add_user)

        edit_btn = QPushButton("✏️ Редактировать")
        edit_btn.clicked.connect(self._edit_user)

        del_btn = QPushButton("🗑️ Удалить")
        del_btn.setProperty("class", "Danger")
        del_btn.clicked.connect(self._delete_user)

        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(edit_btn)
        btn_layout.addWidget(del_btn)
        btn_layout.addStretch()

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)
        self.refresh()

    def refresh(self) -> None:
        users = self.ctx.users.list_users()
        self.table.setRowCount(len(users))
        for r, u in enumerate(users):
            id_item = QTableWidgetItem(str(u["id"]))
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            id_item.setData(Qt.ItemDataRole.UserRole, u)
            self.table.setItem(r, 0, id_item)
            self.table.setItem(r, 1, QTableWidgetItem(u["username"]))
            self.table.setItem(r, 2, QTableWidgetItem(u["full_name"]))
            self.table.setItem(r, 3, QTableWidgetItem(ROLE_LABELS.get(u["role"], u["role"])))
            status_text = "Активен" if u["is_active"] else "Заблокирован"
            st_item = QTableWidgetItem(status_text)
            st_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 4, st_item)

    def _selected_user(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _add_user(self) -> None:
        dlg = UserEditDialog(is_new=True, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            try:
                self.ctx.users.create_user(
                    username=data["username"],
                    full_name=data["full_name"],
                    password=data["password"],
                    role=data["role"],
                )
                self.refresh()
                show_info(self, "Успех", f"Пользователь «{data['username']}» создан.")
            except WMError as exc:
                show_error(self, "Ошибка создания", str(exc))

    def _edit_user(self) -> None:
        u = self._selected_user()
        if not u:
            show_warning(self, "Внимание", "Выберите пользователя из списка.")
            return
        dlg = UserEditDialog(is_new=False, user_data=u, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            try:
                self.ctx.users.update_user(
                    user_id=u["id"],
                    full_name=data["full_name"],
                    role=data["role"],
                    is_active=data["is_active"],
                    password=data["password"] if data["password"] else None,
                )
                self.refresh()
                show_info(self, "Успех", "Данные пользователя обновлены.")
            except WMError as exc:
                show_error(self, "Ошибка обновления", str(exc))

    def _delete_user(self) -> None:
        u = self._selected_user()
        if not u:
            show_warning(self, "Внимание", "Выберите пользователя из списка.")
            return
        if not confirm_dialog(
            self,
            "Подтверждение",
            f"Вы уверены, что хотите удалить пользователя «{u['username']}»?",
        ):
            return
        try:
            self.ctx.users.delete_user(u["id"])
            self.refresh()
            show_info(self, "Успех", "Пользователь удален.")
        except WMError as exc:
            show_error(self, "Ошибка удаления", str(exc))
