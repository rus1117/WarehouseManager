"""Стили оформления интерфейса: светлая и тёмная темы, шрифты и цветовая палитра."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

LIGHT_PALETTE = {
    "bg_main": "#F1F5F9",
    "bg_surface": "#FFFFFF",
    "bg_sidebar": "#0F172A",
    "bg_sidebar_hover": "#1E293B",
    "bg_sidebar_active": "#2563EB",
    "text_main": "#0F172A",
    "text_muted": "#64748B",
    "text_sidebar": "#CBD5E1",
    "text_sidebar_active": "#FFFFFF",
    "border": "#CBD5E1",
    "border_light": "#E2E8F0",
    "border_focus": "#2563EB",
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "primary_text": "#FFFFFF",
    "danger": "#EF4444",
    "danger_hover": "#DC2626",
    "success": "#10B981",
    "warning": "#F59E0B",
    "table_header": "#E2E8F0",
    "table_header_text": "#334155",
    "table_alt_row": "#F8FAFC",
    "table_selected": "#DBEAFE",
    "table_selected_text": "#1E3A8A",
    "input_bg": "#FFFFFF",
    "input_disabled": "#F1F5F9",
}

DARK_PALETTE = {
    "bg_main": "#0F172A",
    "bg_surface": "#1E293B",
    "bg_sidebar": "#090D16",
    "bg_sidebar_hover": "#1E293B",
    "bg_sidebar_active": "#2563EB",
    "text_main": "#F8FAFC",
    "text_muted": "#94A3B8",
    "text_sidebar": "#94A3B8",
    "text_sidebar_active": "#FFFFFF",
    "border": "#334155",
    "border_light": "#1E293B",
    "border_focus": "#3B82F6",
    "primary": "#3B82F6",
    "primary_hover": "#2563EB",
    "primary_text": "#FFFFFF",
    "danger": "#EF4444",
    "danger_hover": "#DC2626",
    "success": "#10B981",
    "warning": "#F59E0B",
    "table_header": "#0F172A",
    "table_header_text": "#CBD5E1",
    "table_alt_row": "#172033",
    "table_selected": "#1E3A8A",
    "table_selected_text": "#FFFFFF",
    "input_bg": "#0F172A",
    "input_disabled": "#1E293B",
}


def apply_app_palette(theme: str = "light") -> None:
    """Устанавливает стиль Fusion и системную палитру QPalette, чтобы Windows Dark Mode не ломал цвета."""
    app = QApplication.instance()
    if app is None:
        return
    app.setStyle("Fusion")
    p = DARK_PALETTE if theme == "dark" else LIGHT_PALETTE

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(p["bg_main"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(p["text_main"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(p["bg_surface"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(p["table_alt_row"]))
    pal.setColor(QPalette.ColorRole.Mid, QColor(p["border"]))
    pal.setColor(QPalette.ColorRole.Dark, QColor(p["border"]))
    pal.setColor(QPalette.ColorRole.Shadow, QColor(p["border"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(p["bg_surface"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(p["text_main"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(p["text_main"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(p["bg_surface"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(p["text_main"]))
    pal.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(p["table_selected"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(p["table_selected_text"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(p["text_muted"]))
    app.setPalette(pal)


def build_qss(theme: str = "light") -> str:
    p = DARK_PALETTE if theme == "dark" else LIGHT_PALETTE
    return f"""
    * {{
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
        font-size: 13px;
        color: {p["text_main"]};
    }}
    QMainWindow, QDialog, QMessageBox {{
        background-color: {p["bg_main"]};
    }}
    QWidget#CentralWidget, QStackedWidget, QWidget#WorkArea, QWidget#PageView {{
        background-color: {p["bg_main"]};
    }}
    QScrollArea, QScrollArea > QWidget > QWidget {{
        background-color: {p["bg_main"]};
        border: none;
    }}
    QWidget#SidebarPanel {{
        background-color: {p["bg_sidebar"]};
        border-right: 1px solid {p["border"]};
    }}
    QFrame#UserCard {{
        background-color: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
    }}
    QPushButton#SwitchUserBtn {{
        background-color: #334155;
        border: 1px solid #475569;
        border-radius: 5px;
        color: #F8FAFC;
        font-size: 11px;
        font-weight: 500;
        padding: 5px 8px;
    }}
    QPushButton#SwitchUserBtn:hover {{
        background-color: #475569;
        border-color: #60A5FA;
        color: #FFFFFF;
    }}
    QFrame.Card {{
        background-color: {p["bg_surface"]};
        border: 1px solid {p["border"]};
        border-radius: 8px;
    }}
    QLabel.PageTitle {{
        font-size: 20px;
        font-weight: 700;
        color: {p["text_main"]};
        background: transparent;
    }}
    QLabel.PageSubtitle {{
        font-size: 13px;
        color: {p["text_muted"]};
        background: transparent;
    }}
    QLabel.SectionTitle {{
        font-size: 15px;
        font-weight: 600;
        color: {p["text_main"]};
        background: transparent;
    }}
    QLabel.StatValue {{
        font-size: 24px;
        font-weight: 700;
        color: {p["text_main"]};
        background: transparent;
    }}
    QLabel.StatLabel {{
        font-size: 13px;
        font-weight: 500;
        color: {p["text_muted"]};
        background: transparent;
    }}
    QLabel {{
        background: transparent;
    }}
    QGroupBox {{
        background-color: {p["bg_surface"]};
        border: 1px solid {p["border"]};
        border-radius: 8px;
        margin-top: 10px;
        padding: 18px 14px 12px 14px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        top: 2px;
        padding: 1px 8px;
        border-radius: 4px;
        color: {p["primary"]};
        background-color: {p["bg_surface"]};
        border: 1px solid {p["border"]};
        font-weight: 700;
        font-size: 12px;
    }}
    QPushButton {{
        background-color: {p["bg_surface"]};
        border: 1px solid {p["border"]};
        border-radius: 6px;
        padding: 6px 14px;
        font-weight: 500;
        color: {p["text_main"]};
    }}
    QPushButton:hover {{
        background-color: {p["table_header"]};
        border-color: {p["border_focus"]};
    }}
    QPushButton:pressed {{
        background-color: {p["border"]};
    }}
    QPushButton:disabled {{
        background-color: {p["input_disabled"]};
        color: {p["text_muted"]};
        border-color: {p["border_light"]};
    }}
    QPushButton.Primary {{
        background-color: {p["primary"]};
        border: 1px solid {p["primary"]};
        color: {p["primary_text"]};
        font-weight: 600;
    }}
    QPushButton.Primary:hover {{
        background-color: {p["primary_hover"]};
        border-color: {p["primary_hover"]};
    }}
    QPushButton.Primary:disabled {{
        background-color: {p["border"]};
        border-color: {p["border"]};
        color: {p["text_muted"]};
    }}
    QPushButton.Danger {{
        background-color: {p["danger"]};
        border: 1px solid {p["danger"]};
        color: #FFFFFF;
        font-weight: 600;
    }}
    QPushButton.Danger:hover {{
        background-color: {p["danger_hover"]};
        border-color: {p["danger_hover"]};
    }}
    QPushButton#SidebarBtn {{
        background-color: transparent;
        border: none;
        border-radius: 6px;
        padding: 9px 12px;
        text-align: left;
        color: {p["text_sidebar"]};
        font-size: 13px;
        font-weight: 500;
    }}
    QPushButton#SidebarBtn:hover {{
        background-color: {p["bg_sidebar_hover"]};
        color: #FFFFFF;
    }}
    QPushButton#SidebarBtn:checked {{
        background-color: {p["bg_sidebar_active"]};
        color: {p["text_sidebar_active"]};
        font-weight: 700;
    }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit, QTextEdit {{
        background-color: {p["input_bg"]};
        border: 1px solid {p["border"]};
        border-radius: 6px;
        padding: 5px 10px;
        color: {p["text_main"]};
        selection-background-color: {p["primary"]};
        selection-color: #FFFFFF;
    }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
        background-color: {p["input_disabled"]};
        color: {p["text_muted"]};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus, QTextEdit:focus {{
        border: 1px solid {p["border_focus"]};
    }}
    QComboBox QAbstractItemView {{
        background-color: {p["bg_surface"]};
        border: 1px solid {p["border"]};
        color: {p["text_main"]};
        selection-background-color: {p["table_selected"]};
        selection-color: {p["table_selected_text"]};
        outline: 0;
    }}
    QRadioButton, QCheckBox {{
        background: transparent;
        color: {p["text_main"]};
        spacing: 6px;
    }}
    QCheckBox::indicator:unchecked {{
        width: 16px;
        height: 16px;
        border: 1px solid {p["border"]};
        border-radius: 3px;
        background-color: {p["input_bg"]};
    }}
    QCheckBox::indicator:unchecked:hover {{
        border: 1px solid {p["border_focus"]};
    }}
    QRadioButton::indicator:unchecked {{
        width: 16px;
        height: 16px;
        border: 1px solid {p["border"]};
        border-radius: 8px;
        background-color: {p["input_bg"]};
    }}
    QRadioButton::indicator:unchecked:hover {{
        border: 1px solid {p["border_focus"]};
    }}
    QRadioButton::indicator:checked {{
        width: 10px;
        height: 10px;
        border: 4px solid {p["primary"]};
        border-radius: 8px;
        background-color: #FFFFFF;
    }}
    QTableView, QTableWidget {{
        background-color: {p["bg_surface"]};
        border: 1px solid {p["border"]};
        border-radius: 6px;
        gridline-color: {p["border_light"]};
        selection-background-color: {p["table_selected"]};
        selection-color: {p["table_selected_text"]};
        alternate-background-color: {p["table_alt_row"]};
        outline: 0;
    }}
    QTableView::item, QTableWidget::item {{
        padding: 4px 8px;
        color: {p["text_main"]};
    }}
    QTableView::item:selected, QTableWidget::item:selected {{
        background-color: {p["table_selected"]};
        color: {p["table_selected_text"]};
    }}
    QWidget.CellContainer {{
        background: transparent;
    }}
    QHeaderView {{
        background-color: {p["table_header"]};
        border: none;
    }}
    QHeaderView::section {{
        background-color: {p["table_header"]};
        border: none;
        border-bottom: 1px solid {p["border"]};
        border-right: 1px solid {p["border"]};
        padding: 6px 8px;
        font-weight: 600;
        color: {p["table_header_text"]};
    }}
    QTableCornerButton::section {{
        background-color: {p["table_header"]};
        border: none;
        border-bottom: 1px solid {p["border"]};
        border-right: 1px solid {p["border"]};
    }}
    QMenu {{
        background-color: {p["bg_surface"]};
        border: 1px solid {p["border"]};
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 24px 6px 12px;
        border-radius: 4px;
        color: {p["text_main"]};
    }}
    QMenu::item:selected {{
        background-color: {p["table_selected"]};
        color: {p["table_selected_text"]};
    }}
    QScrollBar:vertical {{
        background: {p["bg_main"]};
        width: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {p["border"]};
        min-height: 24px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {p["text_muted"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background: {p["bg_main"]};
        height: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background: {p["border"]};
        min-width: 24px;
        border-radius: 5px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {p["text_muted"]};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    QTabWidget::pane {{
        border: none;
        background-color: {p["bg_main"]};
    }}
    QTabBar {{
        background-color: {p["bg_main"]};
    }}
    QTabBar::tab {{
        background: {p["table_header"]};
        color: {p["text_muted"]};
        border: 1px solid {p["border"]};
        padding: 7px 14px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        background: {p["bg_surface"]};
        color: {p["text_main"]};
        border-bottom-color: {p["bg_surface"]};
        font-weight: 700;
    }}
    """
