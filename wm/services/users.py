"""Сервис управления пользователями и аутентификации."""
from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from wm.core.errors import PermissionDenied, ValidationError
from wm.core.security import (
    CurrentUser,
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_VIEWER,
    hash_password,
    validate_password,
    validate_username,
    verify_password,
    P_USERS,
)
from wm.db.models import User, utcnow
from wm.services.common import log_change

if TYPE_CHECKING:
    from wm.app_context import AppContext


class UserService:
    def __init__(self, ctx: "AppContext") -> None:
        self.ctx = ctx

    def init_default_admin_if_empty(self) -> None:
        """Если пользователей в базе нет, создаём первого администратора admin / admin123."""
        with self.ctx.db.session() as s:
            count = s.scalar(select(func.count(User.id)))
            if count == 0:
                admin = User(
                    username="admin",
                    full_name="Главный администратор",
                    password_hash=hash_password("admin123"),
                    role=ROLE_ADMIN,
                    is_active=True,
                )
                s.add(admin)

    def authenticate(self, username: str, password: str) -> CurrentUser:
        username = (username or "").strip()
        with self.ctx.db.session() as s:
            user = s.scalar(select(User).where(User.username == username))
            if not user:
                raise ValidationError("Неверное имя пользователя или пароль.")

            if not user.is_active:
                raise PermissionDenied("Учетная запись заблокирована администратором.")

            now = utcnow()
            if user.locked_until and user.locked_until > now:
                mins = int((user.locked_until - now).total_seconds() / 60) + 1
                raise PermissionDenied(
                    f"Аккаунт временно заблокирован из-за неверных попыток входа. Попробуйте через {mins} мин."
                )

            if not verify_password(password, user.password_hash):
                user.failed_attempts += 1
                threshold = int(self.ctx.settings.get("lockout_threshold", 5))
                lock_mins = int(self.ctx.settings.get("lockout_minutes", 15))
                if user.failed_attempts >= threshold:
                    user.locked_until = now + dt.timedelta(minutes=lock_mins)
                    user.failed_attempts = 0
                raise ValidationError("Неверное имя пользователя или пароль.")

            user.failed_attempts = 0
            user.locked_until = None
            user.last_login = now
            current = CurrentUser(
                id=user.id,
                username=user.username,
                full_name=user.full_name,
                role=user.role,
            )
            log_change(s.connection(), user.username, "user_login")
            return current

    def list_users(self) -> list[dict]:
        self.ctx.session.require(P_USERS)
        with self.ctx.db.session() as s:
            rows = s.scalars(select(User).order_by(User.username)).all()
            return [
                {
                    "id": u.id,
                    "username": u.username,
                    "full_name": u.full_name,
                    "role": u.role,
                    "is_active": u.is_active,
                    "created_at": u.created_at,
                    "last_login": u.last_login,
                }
                for u in rows
            ]

    def create_user(
        self, username: str, full_name: str, password: str, role: str
    ) -> int:
        self.ctx.session.require(P_USERS)
        username = validate_username(username)
        validate_password(password)
        if role not in (ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER):
            raise ValidationError("Недопустимая роль пользователя.")

        with self.ctx.db.session() as s:
            exist = s.scalar(select(User).where(User.username == username))
            if exist:
                raise ValidationError(f"Пользователь «{username}» уже существует.")
            new_user = User(
                username=username,
                full_name=full_name.strip(),
                password_hash=hash_password(password),
                role=role,
                is_active=True,
            )
            s.add(new_user)
            s.flush()
            log_change(
                s.connection(),
                self.ctx.session.username,
                "user_create",
                details={"username": username, "role": role},
            )
            return new_user.id

    def update_user(
        self,
        user_id: int,
        full_name: str,
        role: str,
        is_active: bool,
        password: str | None = None,
    ) -> None:
        self.ctx.session.require(P_USERS)
        if role not in (ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER):
            raise ValidationError("Недопустимая роль пользователя.")

        with self.ctx.db.session() as s:
            user = s.get(User, user_id)
            if not user:
                raise ValidationError("Пользователь не найден.")

            # Нельзя деактивировать самого себя или снять права админа с себя
            if self.ctx.session.user and self.ctx.session.user.id == user_id:
                if not is_active:
                    raise ValidationError("Нельзя деактивировать текущую учетную запись.")
                if role != ROLE_ADMIN:
                    raise ValidationError("Нельзя понизить роль собственной учетной записи.")

            user.full_name = full_name.strip()
            user.role = role
            user.is_active = is_active
            if password:
                validate_password(password)
                user.password_hash = hash_password(password)

            log_change(
                s.connection(),
                self.ctx.session.username,
                "user_update",
                details={"user_id": user_id, "username": user.username, "role": role},
            )

    def delete_user(self, user_id: int) -> None:
        self.ctx.session.require(P_USERS)
        if self.ctx.session.user and self.ctx.session.user.id == user_id:
            raise ValidationError("Нельзя удалить собственную учетную запись.")

        with self.ctx.db.session() as s:
            user = s.get(User, user_id)
            if not user:
                return
            # Проверим, не последний ли это активный администратор
            if user.role == ROLE_ADMIN:
                admins_count = s.scalar(
                    select(func.count(User.id)).where(
                        User.role == ROLE_ADMIN, User.is_active.is_(True)
                    )
                )
                if admins_count <= 1:
                    raise ValidationError("Нельзя удалить последнего администратора в системе.")

            s.delete(user)
            log_change(
                s.connection(),
                self.ctx.session.username,
                "user_delete",
                details={"username": user.username},
            )
