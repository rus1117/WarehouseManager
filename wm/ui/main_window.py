"""Главное окно приложения Warehouse Manager."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from wm import APP_NAME, __version__
from wm.ui.dialogs.login_dialog import LoginDialog
from wm.ui.styles import apply_app_palette, build_qss
from wm.ui.views.backup_view import BackupView
from wm.ui.views.create_table_view import CreateTableView
from wm.ui.views.dashboard_view import DashboardView
from wm.ui.views.export_view import ExportView
from wm.ui.views.import_view import ImportView
from wm.ui.views.search_view import SearchView
from wm.ui.views.settings_view import SettingsView
from wm.ui.views.table_editor_view import TableEditorView
from wm.ui.views.tables_view import TablesView

if TYPE_CHECKING:
    from wm.app_context import AppContext


class MainWindow(QMainWindow):
    def __init__(self, ctx: "AppContext") -> None:
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.resize(1180, 740)
        self.setMinimumSize(940, 620)

        # Словарь открытых вкладок редакторов таблиц: table_id -> TableEditorView
        self.open_table_views: dict[int, TableEditorView] = {}

        # Корневой центральный виджет
        central_widget = QWidget()
        central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Боковая панель (Sidebar)
        sidebar = QWidget()
        sidebar.setObjectName("SidebarPanel")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 16, 12, 16)
        sidebar_layout.setSpacing(6)

        # Логотип / Название
        logo_label = QLabel("📦 Warehouse")
        logo_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold; padding: 4px 6px;")
        sidebar_layout.addWidget(logo_label)

        sub_logo = QLabel("Manager v" + __version__)
        sub_logo.setStyleSheet("color: #94A3B8; font-size: 11px; padding-left: 8px; margin-bottom: 12px;")
        sidebar_layout.addWidget(sub_logo)

        # Кнопки навигации (8 разделов из ТЗ)
        self.nav_btn_group = QButtonGroup(self)
        self.nav_btn_group.setExclusive(True)

        self.btn_dashboard = self._add_nav_btn(sidebar_layout, "🏠  Главная", "dashboard")
        self.btn_tables = self._add_nav_btn(sidebar_layout, "📁  Мои таблицы", "tables")
        self.btn_create = self._add_nav_btn(sidebar_layout, "＋  Создать таблицу", "create_table")
        self.btn_search = self._add_nav_btn(sidebar_layout, "🔍  Поиск", "search")
        self.btn_import = self._add_nav_btn(sidebar_layout, "📥  Импорт данных", "import")
        self.btn_export = self._add_nav_btn(sidebar_layout, "📤  Экспорт данных", "export")
        self.btn_backup = self._add_nav_btn(sidebar_layout, "🛡️  Резервные копии", "backup")
        self.btn_settings = self._add_nav_btn(sidebar_layout, "⚙️  Настройки", "settings")

        sidebar_layout.addStretch()

        # Информация о пользователе внизу сайдбара
        user_card = QFrame()
        user_card.setObjectName("UserCard")
        user_layout = QVBoxLayout(user_card)
        user_layout.setContentsMargins(10, 10, 10, 10)
        user_layout.setSpacing(4)

        self.user_lbl = QLabel("Пользователь")
        self.user_lbl.setStyleSheet("color: #FFFFFF; font-weight: 700; font-size: 12px;")
        user_layout.addWidget(self.user_lbl)

        self.role_lbl = QLabel("Роль")
        self.role_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; margin-bottom: 2px;")
        user_layout.addWidget(self.role_lbl)

        switch_user_btn = QPushButton("Сменить пользователя")
        switch_user_btn.setObjectName("SwitchUserBtn")
        switch_user_btn.clicked.connect(self._switch_user)
        user_layout.addWidget(switch_user_btn)

        sidebar_layout.addWidget(user_card)
        main_layout.addWidget(sidebar)

        # 2. Основная рабочая область: Табы для страниц и открытых таблиц
        self.work_area = QWidget()
        self.work_area.setObjectName("WorkArea")
        work_layout = QVBoxLayout(self.work_area)
        work_layout.setContentsMargins(0, 0, 0, 0)
        work_layout.setSpacing(0)

        # Стек основных страниц
        self.stack = QStackedWidget()

        self.view_dashboard = DashboardView(
            self.ctx,
            on_navigate=self.navigate_to,
            on_open_table=self.open_table,
            on_create_warehouse=self._create_warehouse_table,
        )
        self.view_tables = TablesView(
            self.ctx,
            on_open_table=self.open_table,
            on_create_table=lambda: self.navigate_to("create_table"),
            on_table_deleted=self.close_table_tab,
        )
        self.view_create = CreateTableView(self.ctx, on_table_created=self.open_table)
        self.view_search = SearchView(self.ctx, on_open_table=self.open_table)
        self.view_import = ImportView(self.ctx, on_table_imported=self.open_table)
        self.view_export = ExportView(self.ctx)
        self.view_backup = BackupView(self.ctx)
        self.view_settings = SettingsView(self.ctx, on_theme_changed=self.apply_theme)

        # Вкладки открытых разделов и таблиц
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab)

        # Добавляем стек основных страниц как первую неудаляемую вкладку
        self.tab_widget.addTab(self.stack, "Разделы")
        tab_bar = self.tab_widget.tabBar()
        tab_bar.setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
        tab_bar.setVisible(False)

        self.stack.addWidget(self.view_dashboard)  # 0
        self.stack.addWidget(self.view_tables)     # 1
        self.stack.addWidget(self.view_create)     # 2
        self.stack.addWidget(self.view_search)     # 3
        self.stack.addWidget(self.view_import)     # 4
        self.stack.addWidget(self.view_export)     # 5
        self.stack.addWidget(self.view_backup)     # 6
        self.stack.addWidget(self.view_settings)   # 7

        work_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self.work_area)

        # Применяем тему
        self.apply_theme(self.ctx.settings.get("theme", "light"))
        self._update_user_display()

        # Выбираем главную страницу
        self.btn_dashboard.setChecked(True)
        self.navigate_to("dashboard")

    def _add_nav_btn(self, layout: QVBoxLayout, title: str, nav_code: str) -> QPushButton:
        btn = QPushButton(title)
        btn.setObjectName("SidebarBtn")
        btn.setCheckable(True)
        btn.clicked.connect(lambda: self.navigate_to(nav_code))
        layout.addWidget(btn)
        self.nav_btn_group.addButton(btn)
        return btn

    def apply_theme(self, theme: str) -> None:
        apply_app_palette(theme)
        self.setStyleSheet(build_qss(theme))

    def _update_user_display(self) -> None:
        user = self.ctx.session.user
        if user:
            self.user_lbl.setText(user.display_name)
            from wm.core.security import ROLE_LABELS
            self.role_lbl.setText(ROLE_LABELS.get(user.role, user.role))

    def _switch_user(self) -> None:
        dlg = LoginDialog(self.ctx, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._update_user_display()
            self.refresh_current_view()

    def navigate_to(self, code: str) -> None:
        self.tab_widget.setCurrentIndex(0)

        nav_map = {
            "dashboard": (0, self.view_dashboard, self.btn_dashboard),
            "tables": (1, self.view_tables, self.btn_tables),
            "create_table": (2, self.view_create, self.btn_create),
            "search": (3, self.view_search, self.btn_search),
            "import": (4, self.view_import, self.btn_import),
            "export": (5, self.view_export, self.btn_export),
            "backup": (6, self.view_backup, self.btn_backup),
            "settings": (7, self.view_settings, self.btn_settings),
        }

        if code in nav_map:
            idx, view, btn = nav_map[code]
            self.stack.setCurrentIndex(idx)
            btn.setChecked(True)
            if hasattr(view, "refresh"):
                view.refresh()

    def refresh_current_view(self) -> None:
        cur_idx = self.tab_widget.currentIndex()
        if cur_idx == 0:
            view = self.stack.currentWidget()
            if hasattr(view, "refresh"):
                view.refresh()
        else:
            w = self.tab_widget.currentWidget()
            if hasattr(w, "refresh"):
                w.refresh()

    def open_table(self, table_id: int) -> None:
        if table_id in self.open_table_views:
            editor = self.open_table_views[table_id]
            idx = self.tab_widget.indexOf(editor)
            if idx >= 0:
                self.tab_widget.setCurrentIndex(idx)
                editor.refresh()
                return

        table = self.ctx.tables.get(table_id)
        editor = TableEditorView(self.ctx, table_id, self)
        self.open_table_views[table_id] = editor
        idx = self.tab_widget.addTab(editor, f"📄 {table.name}")
        self.tab_widget.tabBar().setVisible(self.tab_widget.count() > 1)
        self.tab_widget.setCurrentIndex(idx)

    def _close_tab(self, index: int) -> None:
        if index == 0:
            return
        widget = self.tab_widget.widget(index)
        for tid, ed in list(self.open_table_views.items()):
            if ed == widget:
                del self.open_table_views[tid]
                break
        self.tab_widget.removeTab(index)
        self.tab_widget.tabBar().setVisible(self.tab_widget.count() > 1)
        widget.deleteLater()

    def close_table_tab(self, table_id: int) -> None:
        if table_id in self.open_table_views:
            editor = self.open_table_views[table_id]
            idx = self.tab_widget.indexOf(editor)
            if idx > 0:
                self._close_tab(idx)

    def _create_warehouse_table(self) -> None:
        self.navigate_to("create_table")
        self.view_create.select_warehouse_template()
