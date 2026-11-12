"""Локальное журналирование (только в файл на этом компьютере, без отправки куда-либо)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from wm.core.paths import logs_dir

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    handler = RotatingFileHandler(
        logs_dir() / "app.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    _configured = True
