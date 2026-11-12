"""Модель таблицы данных (QAbstractTableModel) с поддержкой пагинации и inline-редактирования."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from wm.core import types as T
from wm.core.errors import WMError
from wm.db.repository import Condition
from wm.services.common import TableInfo

if TYPE_CHECKING:
    from wm.app_context import AppContext


class TableRecordsModel(QAbstractTableModel):
    def __init__(self, ctx: "AppContext", table: TableInfo, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.table = table
        self.rows: list[tuple] = []
        self.total_count: int = 0

        # Состояние запроса
        self.conditions: list[Condition] = []
        self.quick_search: str = ""
        self.sort_col_id: int | None = None
        self.sort_desc: bool = False
        self.limit: int = int(self.ctx.settings.get("page_size", 200))
        self.page: int = 0

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        # +1 для отображения системного ID/№ строки
        return len(self.table.columns) + 1

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if section == 0:
                return "№"
            col = self.table.columns[section - 1]
            return col.name
        return str(self.page * self.limit + section + 1)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        row_tuple = self.rows[index.row()]
        # row_tuple: (_id, col1, col2, ...)

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if index.column() == 0:
                return str(row_tuple[0])
            col_idx = index.column() - 1
            col = self.table.columns[col_idx]
            raw_val = row_tuple[col_idx + 1]
            if role == Qt.ItemDataRole.EditRole:
                return T.to_edit_text(col.type, raw_val)
            return T.to_display(col.type, raw_val)

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if index.column() == 0:
                return Qt.AlignmentFlag.AlignCenter
            col = self.table.columns[index.column() - 1]
            if col.type in (T.INTEGER, T.FLOAT, T.MONEY):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            if col.type in (T.DATE, T.TIME, T.DATETIME, T.BOOL):
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        if role == Qt.ItemDataRole.UserRole:
            # Возвращаем фактический row_id
            return row_tuple[0]

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() > 0 and self.ctx.session.can("data.write"):
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole or index.column() == 0:
            return False
        row_id = self.rows[index.row()][0]
        col = self.table.columns[index.column() - 1]
        try:
            new_storage = self.ctx.records.update_cell(self.table.id, row_id, col.id, value)
            # Обновляем локально в кэше строк без полной перезагрузки
            row_list = list(self.rows[index.row()])
            row_list[index.column()] = new_storage
            self.rows[index.row()] = tuple(row_list)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
            return True
        except WMError:
            return False

    def reload(self) -> None:
        self.beginResetModel()
        self.total_count = self.ctx.records.count(
            self.table, self.conditions, self.quick_search
        )
        offset = self.page * self.limit
        self.rows = self.ctx.records.fetch(
            table=self.table,
            conditions=self.conditions,
            quick=self.quick_search,
            sort_col=self.sort_col_id,
            desc=self.sort_desc,
            limit=self.limit,
            offset=offset,
        )
        self.endResetModel()

    def set_page(self, page: int) -> None:
        self.page = max(0, page)
        self.reload()

    def set_filter(self, conditions: list[Condition], quick: str = "") -> None:
        self.conditions = conditions
        self.quick_search = quick
        self.page = 0
        self.reload()

    def set_sorting(self, col_id: int | None, desc: bool) -> None:
        self.sort_col_id = col_id
        self.sort_desc = desc
        self.reload()

    def get_row_id(self, row_idx: int) -> int | None:
        if 0 <= row_idx < len(self.rows):
            return self.rows[row_idx][0]
        return None
