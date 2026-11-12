"""Точка входа в приложение Warehouse Manager."""
from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

# Добавляем корень проекта в sys.path при прямом запуске
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from wm.app_context import AppContext
from wm.core.logging_setup import setup_logging
from wm.ui.dialogs.login_dialog import LoginDialog
from wm.ui.main_window import MainWindow
from wm.ui.styles import apply_app_palette, build_qss

log = logging.getLogger(__name__)


def _install_excepthook() -> None:
    def _excepthook(exc_type, exc_value, exc_tb):
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log.error("Неперехваченное исключение:\n%s", tb_text)
        if QApplication.instance() is not None:
            QMessageBox.critical(
                None,
                "Ошибка приложения",
                f"Произошла непредвиденная ошибка:\n{exc_value}",
            )
        else:
            sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook


def main() -> int:
    setup_logging()
    _install_excepthook()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Warehouse Manager")
    app.setOrganizationName("WarehouseManager")

    ctx = AppContext()
    try:
        ctx.initialize()
    except Exception as exc:
        log.exception("Критическая ошибка инициализации базы данных")
        QMessageBox.critical(None, "Ошибка запуска", f"Не удалось открыть базу данных:\n{exc}")
        return 1

    theme = ctx.settings.get("theme", "light")
    apply_app_palette(theme)
    app.setStyleSheet(build_qss(theme))

    login_dlg = LoginDialog(ctx)
    if login_dlg.exec() != QDialog.DialogCode.Accepted:
        ctx.shutdown()
        return 0

    window = MainWindow(ctx)
    window.show()

    ret = app.exec()
    ctx.shutdown()
    return ret


if __name__ == "__main__":
    sys.exit(main())
