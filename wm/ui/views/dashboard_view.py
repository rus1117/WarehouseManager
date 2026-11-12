"""Раздел «Главная» (Dashboard) с метриками и быстрыми действиями."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wm.ui.common import Card

if TYPE_CHECKING:
    from wm.app_context import AppContext


class StatCard(Card):
    def __init__(self, title: str, value: str = "0", icon_text: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setProperty("class", "StatLabel")
        header.addWidget(title_lbl)
        header.addStretch()

        if icon_text:
            ico = QLabel(icon_text)
            ico.setStyleSheet("font-size: 16px;")
            header.addWidget(ico)

        layout.addLayout(header)

        self.val_lbl = QLabel(value)
        self.val_lbl.setProperty("class", "StatValue")
        layout.addWidget(self.val_lbl)

    def set_value(self, val: str) -> None:
        self.val_lbl.setText(val)


class DashboardView(QWidget):
    def __init__(
        self,
        ctx: "AppContext",
        on_navigate: Callable[[str], None],
        on_open_table: Callable[[int], None],
        on_create_warehouse: Callable[[], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PageView")
        self.ctx = ctx
        self.on_navigate = on_navigate
        self.on_open_table = on_open_table
        self.on_create_warehouse = on_create_warehouse

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(18)

        # Приветствие
        greeting_layout = QVBoxLayout()
        greeting_layout.setSpacing(3)
        self.welcome_lbl = QLabel("Warehouse Manager")
        self.welcome_lbl.setProperty("class", "PageTitle")
        greeting_layout.addWidget(self.welcome_lbl)

        sub_lbl = QLabel("Универсальная система управления таблицами и складским учётом")
        sub_lbl.setProperty("class", "PageSubtitle")
        greeting_layout.addWidget(sub_lbl)
        layout.addLayout(greeting_layout)

        # Карточки статистики
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(14)

        self.tables_count_card = StatCard("Всего таблиц", "0", "📊")
        self.records_count_card = StatCard("Всего записей", "0", "📝")
        self.db_size_card = StatCard("Размер базы", "0 МБ", "💾")
        self.backups_card = StatCard("Резервных копий", "0", "🛡️")

        stats_layout.addWidget(self.tables_count_card)
        stats_layout.addWidget(self.records_count_card)
        stats_layout.addWidget(self.db_size_card)
        stats_layout.addWidget(self.backups_card)
        layout.addLayout(stats_layout)

        # Быстрые действия
        actions_header = QLabel("Быстрые действия")
        actions_header.setProperty("class", "SectionTitle")
        layout.addWidget(actions_header)

        actions_grid = QGridLayout()
        actions_grid.setSpacing(12)

        wh_btn = QPushButton("📦  Создать складскую таблицу")
        wh_btn.setMinimumHeight(44)
        wh_btn.setProperty("class", "Primary")
        wh_btn.clicked.connect(self.on_create_warehouse)
        actions_grid.addWidget(wh_btn, 0, 0)

        create_btn = QPushButton("＋  Создать универсальную таблицу")
        create_btn.setMinimumHeight(44)
        create_btn.clicked.connect(lambda: self.on_navigate("create_table"))
        actions_grid.addWidget(create_btn, 0, 1)

        import_btn = QPushButton("📥  Импорт из Excel / CSV")
        import_btn.setMinimumHeight(44)
        import_btn.clicked.connect(lambda: self.on_navigate("import"))
        actions_grid.addWidget(import_btn, 1, 0)

        search_btn = QPushButton("🔍  Глобальный поиск")
        search_btn.setMinimumHeight(44)
        search_btn.clicked.connect(lambda: self.on_navigate("search"))
        actions_grid.addWidget(search_btn, 1, 1)

        layout.addLayout(actions_grid)

        # Последние активные таблицы
        recent_header = QLabel("Недавние таблицы")
        recent_header.setProperty("class", "SectionTitle")
        layout.addWidget(recent_header)

        self.recent_container = QVBoxLayout()
        self.recent_container.setSpacing(8)
        layout.addLayout(self.recent_container)

        layout.addStretch()

    def refresh(self) -> None:
        user = self.ctx.session.user
        if user:
            self.welcome_lbl.setText(f"Здравствуйте, {user.display_name}!")

        tables = self.ctx.tables.list(include_archived=False, with_counts=True)
        total_records = sum(t.row_count or 0 for t in tables)
        self.tables_count_card.set_value(str(len(tables)))
        self.records_count_card.set_value(f"{total_records:,}".replace(",", " "))

        size_mb = self.ctx.db.size_bytes() / (1024 * 1024)
        self.db_size_card.set_value(f"{size_mb:.2f} МБ")

        try:
            backups = self.ctx.backup.list_backups()
            self.backups_card.set_value(str(len(backups)))
        except Exception:
            self.backups_card.set_value("0")

        # Очищаем и заполняем список недавних таблиц
        while self.recent_container.count():
            item = self.recent_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        recent = sorted(tables, key=lambda x: x.updated_at, reverse=True)[:5]
        if not recent:
            empty_lbl = QLabel("У вас пока нет созданных таблиц. Нажмите «Создать складскую таблицу», чтобы начать.")
            empty_lbl.setProperty("class", "PageSubtitle")
            self.recent_container.addWidget(empty_lbl)
        else:
            for t in recent:
                card = Card()
                h = QHBoxLayout(card)
                h.setContentsMargins(14, 10, 14, 10)

                v = QVBoxLayout()
                v.setSpacing(2)
                name_lbl = QLabel(t.name)
                name_lbl.setStyleSheet("font-weight: 700; font-size: 14px;")
                sub = QLabel(f"Категория: {t.category or 'Без категории'}  |  Записей: {t.row_count or 0}")
                sub.setProperty("class", "PageSubtitle")
                v.addWidget(name_lbl)
                v.addWidget(sub)
                h.addLayout(v)
                h.addStretch()

                open_btn = QPushButton("Открыть")
                open_btn.setProperty("class", "Primary")
                tid = t.id
                open_btn.clicked.connect(lambda _, x=tid: self.on_open_table(x))
                h.addWidget(open_btn)

                self.recent_container.addWidget(card)
