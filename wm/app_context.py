"""Центральный контекст приложения Warehouse Manager."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from wm.core.paths import db_path, default_backup_dir
from wm.core.security import SYSTEM, CurrentUser, Session
from wm.db.engine import Database
from wm.services.backup import BackupService
from wm.services.exporter import ExportService
from wm.services.importer import ImportService
from wm.services.records import RecordService
from wm.services.search import SearchService
from wm.services.settings import SettingsService
from wm.services.tables import TableService
from wm.services.users import UserService


class AppContext:
    def __init__(self, db_file: Path | str | None = None, backup_dir: Path | None = None) -> None:
        self.db_file = Path(db_file) if db_file else db_path()
        self.default_backup_dir = backup_dir or default_backup_dir()

        self.db = Database(self.db_file, backup_dir=self.default_backup_dir)
        self.session = Session()

        # Сервисы
        self.settings = SettingsService(self)
        self.users = UserService(self)
        self.tables = TableService(self)
        self.records = RecordService(self)
        self.search = SearchService(self)
        self.importer = ImportService(self)
        self.exporter = ExportService(self)
        self.backup = BackupService(self)

    def initialize(self) -> None:
        self.db.open()
        # Инициализируем настройки
        self.settings.load_all()
        # Инициализируем дефолтного администратора
        self.users.init_default_admin_if_empty()

    def shutdown(self) -> None:
        self.db.close()
