"""Сервис управления настройками приложения.

Настройки хранятся в таблице wm_settings базы данных в формате JSON.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from wm.core.security import P_SETTINGS
from wm.db.models import Setting

if TYPE_CHECKING:
    from wm.app_context import AppContext

DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "light",  # light | dark
    "page_size": 200,
    "font_size": 10,
    "backup_auto_enabled": True,
    "backup_interval_days": 1,
    "backup_keep_count": 10,
    "backup_dir": "",
    "default_import_dup_mode": "all",
    "lockout_threshold": 5,
    "lockout_minutes": 15,
}


class SettingsService:
    def __init__(self, ctx: "AppContext") -> None:
        self.ctx = ctx
        self._cache: dict[str, Any] = {}
        self._loaded = False

    def load_all(self) -> dict[str, Any]:
        with self.ctx.db.session() as s:
            rows = s.scalars(select(Setting)).all()
            data = dict(DEFAULT_SETTINGS)
            for r in rows:
                try:
                    data[r.key] = json.loads(r.value)
                except (ValueError, TypeError):
                    data[r.key] = r.value
            self._cache = data
            self._loaded = True
            return dict(self._cache)

    def get(self, key: str, default: Any = None) -> Any:
        if not self._loaded:
            self.load_all()
        if default is None:
            default = DEFAULT_SETTINGS.get(key)
        return self._cache.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.ctx.session.require(P_SETTINGS)
        val_json = json.dumps(value, ensure_ascii=False)
        with self.ctx.db.session() as s:
            obj = s.get(Setting, key)
            if obj:
                obj.value = val_json
            else:
                s.add(Setting(key=key, value=val_json))
        self._cache[key] = value

    def set_many(self, values: dict[str, Any]) -> None:
        self.ctx.session.require(P_SETTINGS)
        with self.ctx.db.session() as s:
            for k, v in values.items():
                val_json = json.dumps(v, ensure_ascii=False)
                obj = s.get(Setting, k)
                if obj:
                    obj.value = val_json
                else:
                    s.add(Setting(key=k, value=val_json))
                self._cache[k] = v
