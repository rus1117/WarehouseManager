"""ORM-модели служебных (метаданных) таблиц.

Пользовательские данные хранятся в отдельных физических таблицах ``data_<id>``
со столбцами ``c_<id>`` (см. repository.py). Это даёт индексы SQLite и высокую скорость
на миллионах строк, а имена объектов БД никогда не берутся из пользовательского ввода.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> dt.datetime:
    return dt.datetime.now().replace(microsecond=0)


class Base(DeclarativeBase):
    pass


class Meta(Base):
    """Системная информация: версия схемы, идентификатор базы и т.п."""
    __tablename__ = "wm_meta"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Setting(Base):
    __tablename__ = "wm_settings"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="null")  # JSON


class User(Base):
    __tablename__ = "wm_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    last_login: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class Category(Base):
    __tablename__ = "wm_categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class UserTable(Base):
    __tablename__ = "wm_tables"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32), default="generic")  # generic | warehouse
    physical_name: Mapped[str] = mapped_column(String(64), unique=True, default="")
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("wm_categories.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str] = mapped_column(Text, default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    settings: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[str] = mapped_column(String(64), default="")

    columns: Mapped[list["TableColumn"]] = relationship(
        back_populates="table", cascade="all, delete-orphan", order_by="TableColumn.position"
    )
    category: Mapped[Category | None] = relationship()


class TableColumn(Base):
    __tablename__ = "wm_columns"
    __table_args__ = (UniqueConstraint("table_id", "physical_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("wm_tables.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    physical_name: Mapped[str] = mapped_column(String(64), default="")
    type: Mapped[str] = mapped_column(String(32))
    position: Mapped[int] = mapped_column(Integer, default=0)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    options: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    width: Mapped[int] = mapped_column(Integer, default=0)
    indexed: Mapped[bool] = mapped_column(Boolean, default=False)

    table: Mapped[UserTable] = relationship(back_populates="columns")


class ChangeLog(Base):
    """История изменений."""
    __tablename__ = "wm_history"
    __table_args__ = (Index("ix_history_table_row", "table_id", "row_id"),
                      Index("ix_history_ts", "ts"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    username: Mapped[str] = mapped_column(String(64), default="")
    table_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(32))
    details: Mapped[str] = mapped_column(Text, default="{}")  # JSON


class SavedFilter(Base):
    __tablename__ = "wm_saved_filters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("wm_tables.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    definition: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
