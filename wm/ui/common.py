"""Общие вспомогательные компоненты UI."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def confirm_dialog(parent: QWidget, title: str, text: str) -> bool:
    res = QMessageBox.question(
        parent,
        title,
        text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return res == QMessageBox.StandardButton.Yes


def show_error(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.critical(parent, title, text)


def show_info(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


def show_warning(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


class Card(QFrame):
    """Стилизованная карточка с границами и фоном."""
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("class", "Card")
        self.setFrameShape(QFrame.Shape.StyledPanel)


class PageHeader(QWidget):
    """Заголовок раздела страницы с описанием и кнопками действий."""
    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 16)

        text_layout = QVBoxLayout()
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-size: 20px; font-weight: bold;")
        text_layout.addWidget(self.title_lbl)

        if subtitle:
            self.sub_lbl = QLabel(subtitle)
            self.sub_lbl.setStyleSheet("color: #64748B; font-size: 13px;")
            text_layout.addWidget(self.sub_lbl)

        layout.addLayout(text_layout)
        layout.addStretch()

        self.actions_layout = QHBoxLayout()
        layout.addLayout(self.actions_layout)

    def add_action_button(self, btn: QPushButton) -> None:
        self.actions_layout.addWidget(btn)


class ProgressDialog(QDialog):
    """Диалог отображения прогресса длительных операций с кнопкой отмены."""
    def __init__(self, title: str, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)
        self.is_cancelled = False

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.label = QLabel(label)
        layout.addWidget(self.label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(self.cancel_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def update_progress(self, current: int, total: int, msg: str = "") -> None:
        if total > 0:
            pct = min(100, max(0, int((current / total) * 100)))
            self.progress_bar.setValue(pct)
        if msg:
            self.label.setText(msg)

    def _on_cancel(self) -> None:
        self.is_cancelled = True
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("Отмена...")
