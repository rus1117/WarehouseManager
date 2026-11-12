"""Определение расположения программы и пользовательских данных.

Режимы:
* Portable — рядом с EXE лежит файл ``portable.txt``: данные хранятся в ``<папка EXE>/data``.
* Установленный — данные хранятся в ``%LOCALAPPDATA%/WarehouseManager``.
* Запуск из исходников — данные в ``<корень проекта>/data``.
* Переменная окружения ``WM_DATA_DIR`` принудительно задаёт папку данных (тесты, особые случаи).

Пользовательские данные НИКОГДА не размещаются во временной папке PyInstaller (sys._MEIPASS).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from wm import APP_ID

PORTABLE_MARKER = "portable.txt"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_base_dir() -> Path:
    """Папка, где лежит EXE (или корень проекта при запуске из исходников)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resource_dir() -> Path:
    """Папка ресурсов, упакованных внутрь EXE (только для чтения)."""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "wm" / "resources"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1] / "resources"


def is_portable() -> bool:
    if os.environ.get("WM_PORTABLE") == "1":
        return True
    if not is_frozen():
        return True
    return (app_base_dir() / PORTABLE_MARKER).exists()


def data_dir() -> Path:
    override = os.environ.get("WM_DATA_DIR")
    if override:
        path = Path(override)
    elif is_portable():
        path = app_base_dir() / "data"
    else:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(base) / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "warehouse.db"


def default_backup_dir() -> Path:
    path = data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
