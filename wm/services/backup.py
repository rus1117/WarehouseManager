"""Резервное копирование и восстановление базы данных SQLite.

Использует штатный SQLite Online Backup API (через sqlite3.Connection.backup),
который не блокирует работу приложения и создаёт консистентный снапшот
даже во время активных транзакций WAL.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from wm.core.errors import NotFound, StorageError, ValidationError, translate_os_error
from wm.core.security import P_BACKUP_CREATE, P_BACKUP_RESTORE
from wm.services.common import log_change

if TYPE_CHECKING:
    from wm.app_context import AppContext

log = logging.getLogger(__name__)

ProgressCb = Callable[[int, int, str], None]


@dataclass
class BackupInfo:
    filename: str
    path: Path
    size_bytes: int
    created_at: dt.datetime
    is_valid: bool = True


class BackupService:
    def __init__(self, ctx: "AppContext") -> None:
        self.ctx = ctx

    @property
    def backup_dir(self) -> Path:
        custom = self.ctx.settings.get("backup_dir")
        if custom:
            p = Path(custom)
            p.mkdir(parents=True, exist_ok=True)
            return p
        return self.ctx.default_backup_dir

    def list_backups(self) -> list[BackupInfo]:
        self.ctx.session.require(P_BACKUP_CREATE)
        b_dir = self.backup_dir
        if not b_dir.exists():
            return []
        items = []
        for file in b_dir.glob("wm_backup_*.db"):
            try:
                stat = file.stat()
                # Извлекаем дату из имени или времени файла
                items.append(
                    BackupInfo(
                        filename=file.name,
                        path=file,
                        size_bytes=stat.st_size,
                        created_at=dt.datetime.fromtimestamp(stat.st_mtime),
                    )
                )
            except OSError:
                continue
        items.sort(key=lambda x: x.created_at, reverse=True)
        return items

    def create_backup(
        self,
        target_path: Path | str | None = None,
        progress: ProgressCb | None = None,
        note: str = "",
    ) -> Path:
        self.ctx.session.require(P_BACKUP_CREATE)
        progress = progress or (lambda *a: None)
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        if target_path:
            dest = Path(target_path)
            if dest.is_dir():
                dest = dest / f"wm_backup_{timestamp}.db"
        else:
            dest = self.backup_dir / f"wm_backup_{timestamp}.db"

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")

        try:
            # Проверка свободного места
            free = shutil.disk_usage(dest.parent).free
            db_size = self.ctx.db.size_bytes()
            if free < db_size + 10_000_000:
                raise StorageError("Недостаточно места на диске для резервной копии.")

            progress(0, 100, "Инициализация резервного копирования...")
            src_conn = sqlite3.connect(self.ctx.db.path)
            dst_conn = sqlite3.connect(tmp)
            try:
                def step_callback(status, remaining, total):
                    done = total - remaining
                    pct = int((done / total) * 100) if total > 0 else 50
                    progress(done, total, f"Копирование: {pct}%")

                with dst_conn:
                    src_conn.backup(dst_conn, pages=250, progress=step_callback)
            finally:
                dst_conn.close()
                src_conn.close()

            # Проверяем целостность созданного бэкапа
            check_conn = sqlite3.connect(tmp)
            try:
                cur = check_conn.cursor()
                res = cur.execute("PRAGMA quick_check").fetchall()
                if not res or res[0][0] != "ok":
                    raise StorageError("Созданная резервная копия не прошла проверку целостности.")
            finally:
                check_conn.close()

            if dest.exists():
                dest.unlink()
            tmp.rename(dest)

            with self.ctx.db.begin() as conn:
                log_change(
                    conn,
                    self.ctx.session.username,
                    "backup_create",
                    details={"path": str(dest), "note": note},
                )
            self.rotate_backups()
            progress(100, 100, "Резервная копия успешно создана.")
            return dest
        except Exception as exc:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            raise translate_os_error(exc)

    def restore_backup(
        self, backup_path: Path | str, progress: ProgressCb | None = None
    ) -> None:
        self.ctx.session.require(P_BACKUP_RESTORE)
        progress = progress or (lambda *a: None)
        path = Path(backup_path)
        if not path.exists():
            raise NotFound(f"Файл резервной копии не найден: {path}")

        # Проверка целостности файла перед восстановлением
        progress(10, 100, "Проверка резервной копии...")
        check_conn = sqlite3.connect(path)
        try:
            res = check_conn.cursor().execute("PRAGMA integrity_check").fetchall()
            if not res or res[0][0] != "ok":
                raise ValidationError("Файл повреждён и не может быть восстановлен.")
            has_meta = check_conn.cursor().execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wm_meta'"
            ).fetchone()
            if not has_meta:
                raise ValidationError("Файл не является базой данных Warehouse Manager.")
        finally:
            check_conn.close()

        progress(30, 100, "Создание страховочной копии текущей базы...")
        # Создаем автоматический бэкап текущего состояния на всякий случай
        safe_copy = self.backup_dir / f"safety_before_restore_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        try:
            shutil.copy2(self.ctx.db.path, safe_copy)
        except OSError:
            pass

        progress(50, 100, "Восстановление данных...")
        self.ctx.db.close()
        try:
            # Заменяем основной файл и удаляем возможные WAL / SHM
            shutil.copy2(path, self.ctx.db.path)
            for ext in ("-wal", "-shm"):
                aux = Path(str(self.ctx.db.path) + ext)
                if aux.exists():
                    aux.unlink()
        finally:
            self.ctx.db.open()

        with self.ctx.db.begin() as conn:
            log_change(
                conn,
                self.ctx.session.username,
                "backup_restore",
                details={"from": str(path), "safety_copy": str(safe_copy)},
            )
        progress(100, 100, "Восстановление завершено.")

    def check_integrity(self, file_path: Path | str | None = None) -> list[str]:
        target = Path(file_path) if file_path else self.ctx.db.path
        if not target.exists():
            return ["Файл не существует."]
        try:
            conn = sqlite3.connect(target)
            try:
                cur = conn.cursor()
                rows = [r[0] for r in cur.execute("PRAGMA integrity_check").fetchall()]
                fk = [str(r) for r in cur.execute("PRAGMA foreign_key_check").fetchall()]
            finally:
                conn.close()
            problems = [r for r in rows if r != "ok"]
            if fk:
                problems += [f"Нарушение внешнего ключа: {item}" for item in fk]
            return problems
        except Exception as exc:
            return [f"Ошибка проверки базы: {exc}"]

    def rotate_backups(self) -> None:
        """Ротация бэкапов согласно политике хранения (max_count)."""
        keep_count = int(self.ctx.settings.get("backup_keep_count", 10))
        if keep_count <= 0:
            return
        backups = self.list_backups()
        if len(backups) > keep_count:
            to_remove = backups[keep_count:]
            for b in to_remove:
                try:
                    b.path.unlink()
                except OSError:
                    log.warning("Не удалось удалить старую резервную копию %s", b.path)
