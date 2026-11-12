"""Подключение к SQLite, настройка надёжности, проверка совместимости и миграции."""
from __future__ import annotations

import logging
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session as OrmSession, sessionmaker

from wm import SCHEMA_VERSION, __version__
from wm.core.errors import IncompatibleDatabase, StorageError
from wm.db.models import Base

log = logging.getLogger(__name__)


def wm_lower(value):
    """Регистронезависимое сравнение с поддержкой кириллицы (встроенный LOWER — только ASCII)."""
    if value is None:
        return None
    return " ".join(str(value).casefold().replace("ё", "е").split())


def _on_connect(dbapi_conn: sqlite3.Connection, _record) -> None:
    dbapi_conn.create_function("wm_lower", 1, wm_lower, deterministic=True)
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=10000")
    cur.execute("PRAGMA journal_mode=WAL")
    # FULL — максимальная защита от потери данных при сбое питания.
    cur.execute("PRAGMA synchronous=FULL")
    cur.execute("PRAGMA temp_store=MEMORY")
    cur.execute("PRAGMA cache_size=-65536")  # ~64 МБ
    cur.close()


# Миграции: номер версии -> функция(conn). Только добавляющие изменения,
# пользовательские данные никогда не удаляются.
MIGRATIONS: dict[int, Callable[[Connection], None]] = {
    # 2: lambda conn: conn.execute(text("ALTER TABLE wm_tables ADD COLUMN color TEXT")),
}


class Database:
    def __init__(self, path: Path | str, backup_dir: Path | None = None) -> None:
        self.path = Path(path)
        self.backup_dir = backup_dir
        self.engine: Engine | None = None
        self._sessionmaker: sessionmaker | None = None

    # ── жизненный цикл ──────────────────────────────────────────────
    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists() and self.path.stat().st_size > 0
        if existed:
            self._check_sqlite_header()
        self.engine = create_engine(
            f"sqlite:///{self.path}", future=True,
            connect_args={"timeout": 30, "check_same_thread": False},
        )
        event.listen(self.engine, "connect", _on_connect)
        self._sessionmaker = sessionmaker(bind=self.engine, expire_on_commit=False)
        try:
            self._prepare_schema(existed)
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self.engine is not None:
            try:
                with self.engine.connect() as conn:
                    conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
                    conn.exec_driver_sql("PRAGMA optimize")
            except Exception:  # noqa: BLE001 — закрытие не должно падать
                log.exception("Ошибка при закрытии базы")
            self.engine.dispose()
            self.engine = None

    def _check_sqlite_header(self) -> None:
        try:
            with open(self.path, "rb") as fh:
                header = fh.read(16)
        except OSError as exc:
            raise StorageError(f"Не удаётся открыть файл базы данных: {exc}") from exc
        if header != b"SQLite format 3\x00":
            raise IncompatibleDatabase(
                f"Файл {self.path} не является базой данных Warehouse Manager или повреждён."
            )

    def _prepare_schema(self, existed: bool) -> None:
        assert self.engine is not None
        with self.engine.begin() as conn:
            has_meta = conn.execute(text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wm_meta'"
            )).first() is not None
            if existed and not has_meta:
                other = conn.execute(text(
                    "SELECT count(*) FROM sqlite_master WHERE type='table'"
                )).scalar()
                if other:
                    raise IncompatibleDatabase("Файл не является базой Warehouse Manager.")
            version = 0
            if has_meta:
                row = conn.execute(text(
                    "SELECT value FROM wm_meta WHERE key='schema_version'")).first()
                version = int(row[0]) if row else 0
            if version > SCHEMA_VERSION:
                raise IncompatibleDatabase(
                    f"База создана более новой версией программы (схема {version}, "
                    f"поддерживается {SCHEMA_VERSION}). Обновите Warehouse Manager. "
                    "Данные не изменялись."
                )
        if has_meta and 0 < version < SCHEMA_VERSION:
            self._backup_before_migration(version)
        with self.engine.begin() as conn:
            Base.metadata.create_all(conn)  # только создаёт недостающие таблицы
            for target in range(max(version, 1) + 1, SCHEMA_VERSION + 1):
                if version and target in MIGRATIONS:
                    log.info("Миграция схемы до версии %s", target)
                    MIGRATIONS[target](conn)
            self._set_meta(conn, "schema_version", str(SCHEMA_VERSION))
            self._set_meta(conn, "app_version", __version__)
            if not conn.execute(text("SELECT 1 FROM wm_meta WHERE key='db_uuid'")).first():
                self._set_meta(conn, "db_uuid", uuid.uuid4().hex)

    def _backup_before_migration(self, version: int) -> None:
        target_dir = self.backup_dir or self.path.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / f"before_migration_v{version}_{uuid.uuid4().hex[:6]}.db"
        src = sqlite3.connect(self.path)
        try:
            dst = sqlite3.connect(dest)
            with dst:
                src.backup(dst)
            dst.close()
        finally:
            src.close()
        log.info("Резервная копия перед миграцией: %s", dest)

    @staticmethod
    def _set_meta(conn: Connection, key: str, value: str) -> None:
        conn.execute(text(
            "INSERT INTO wm_meta(key, value) VALUES(:k, :v) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"), {"k": key, "v": value})

    # ── доступ ─────────────────────────────────────────────────────
    @contextmanager
    def session(self) -> Iterator[OrmSession]:
        """ORM-сессия в транзакции: commit при успехе, rollback при ошибке."""
        assert self._sessionmaker is not None, "База не открыта"
        s = self._sessionmaker()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    @contextmanager
    def begin(self) -> Iterator[Connection]:
        assert self.engine is not None, "База не открыта"
        with self.engine.begin() as conn:
            yield conn

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        assert self.engine is not None, "База не открыта"
        with self.engine.connect() as conn:
            yield conn

    # ── обслуживание ───────────────────────────────────────────────
    def integrity_check(self, quick: bool = False) -> list[str]:
        """Возвращает пустой список, если база в порядке, иначе список проблем."""
        with self.connect() as conn:
            pragma = "quick_check" if quick else "integrity_check"
            rows = [r[0] for r in conn.exec_driver_sql(f"PRAGMA {pragma}")]
            fk = list(conn.exec_driver_sql("PRAGMA foreign_key_check"))
        problems = [r for r in rows if r != "ok"]
        problems += [f"Нарушение внешнего ключа: {tuple(r)}" for r in fk]
        return problems

    def vacuum(self) -> None:
        free = shutil.disk_usage(self.path.parent).free
        if free < self.path.stat().st_size * 2:
            raise StorageError("Недостаточно места на диске для оптимизации базы.")
        with self.connect() as conn:
            conn.exec_driver_sql("VACUUM")

    def size_bytes(self) -> int:
        total = 0
        for suffix in ("", "-wal"):
            p = Path(str(self.path) + suffix)
            if p.exists():
                total += p.stat().st_size
        return total
