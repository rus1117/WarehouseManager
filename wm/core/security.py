"""Безопасность: хэширование паролей, роли и права доступа, текущая сессия."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass, field

from wm.core.errors import PermissionDenied, ValidationError

PBKDF2_ITERATIONS = 310_000

ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"
ROLE_VIEWER = "viewer"

ROLE_LABELS = {
    ROLE_ADMIN: "Администратор",
    ROLE_OPERATOR: "Оператор",
    ROLE_VIEWER: "Только просмотр",
}

# Права доступа
P_DATA_READ = "data.read"
P_DATA_WRITE = "data.write"
P_DATA_PURGE = "data.purge"            # окончательное удаление ПДн по запросу
P_TABLE_CREATE = "table.create"
P_TABLE_STRUCTURE = "table.structure"
P_TABLE_ARCHIVE = "table.archive"
P_TABLE_DELETE = "table.delete"
P_IMPORT = "import"
P_EXPORT = "export"
P_BACKUP_CREATE = "backup.create"
P_BACKUP_RESTORE = "backup.restore"
P_SETTINGS = "settings.manage"
P_USERS = "users.manage"

ROLE_PERMISSIONS: dict[str, set[str]] = {
    ROLE_ADMIN: {
        P_DATA_READ, P_DATA_WRITE, P_DATA_PURGE, P_TABLE_CREATE, P_TABLE_STRUCTURE,
        P_TABLE_ARCHIVE, P_TABLE_DELETE, P_IMPORT, P_EXPORT, P_BACKUP_CREATE,
        P_BACKUP_RESTORE, P_SETTINGS, P_USERS,
    },
    ROLE_OPERATOR: {
        P_DATA_READ, P_DATA_WRITE, P_TABLE_CREATE, P_TABLE_STRUCTURE, P_TABLE_ARCHIVE,
        P_IMPORT, P_EXPORT, P_BACKUP_CREATE,
    },
    ROLE_VIEWER: {P_DATA_READ, P_EXPORT},
}

_USERNAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9_.\-]{3,32}$")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def validate_username(username: str) -> str:
    username = (username or "").strip()
    if not _USERNAME_RE.match(username):
        raise ValidationError(
            "Имя пользователя: 3–32 символа (буквы, цифры, «_», «.», «-»), без пробелов."
        )
    return username


def validate_password(password: str) -> None:
    if len(password or "") < 6:
        raise ValidationError("Пароль должен содержать не менее 6 символов.")
    if password.strip() != password:
        raise ValidationError("Пароль не должен начинаться или заканчиваться пробелом.")


@dataclass
class CurrentUser:
    id: int
    username: str
    full_name: str
    role: str
    permissions: set[str] = field(default_factory=set)

    @property
    def display_name(self) -> str:
        return self.full_name or self.username


class Session:
    """Текущая сессия пользователя. Проверки прав выполняются в сервисном слое."""

    def __init__(self) -> None:
        self.user: CurrentUser | None = None

    def login(self, user: CurrentUser) -> None:
        user.permissions = set(ROLE_PERMISSIONS.get(user.role, set()))
        self.user = user

    def logout(self) -> None:
        self.user = None

    @property
    def username(self) -> str:
        return self.user.username if self.user else "system"

    def can(self, permission: str) -> bool:
        return bool(self.user and permission in self.user.permissions)

    def require(self, permission: str) -> None:
        if not self.can(permission):
            raise PermissionDenied("Недостаточно прав для выполнения этой операции.")


SYSTEM = CurrentUser(0, "system", "Система", ROLE_ADMIN)
