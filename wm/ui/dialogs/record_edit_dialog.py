"""Диалог добавления и редактирования записи таблицы."""
from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QDate, QDateTime, Qt, QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from wm.core import types as T
from wm.core.errors import WMError
from wm.services.common import TableInfo
from wm.services.records import default_display
from wm.ui.common import show_error

if TYPE_CHECKING:
    from wm.app_context import AppContext


class RecordEditDialog(QDialog):
    def __init__(
        self,
        ctx: "AppContext",
        table: TableInfo,
        row_id: int | None = None,
        initial_data: dict[int, Any] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.table = table
        self.row_id = row_id
        self.is_new = row_id is None
        self.add_another = False
        self.widgets: dict[int, QWidget] = {}

        self.setWindowTitle("Новая запись" if self.is_new else f"Редактирование записи №{row_id}")
        self.resize(540, min(680, 120 + len(table.columns) * 48))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        form_host = QWidget()
        form = QFormLayout(form_host)
        form.setContentsMargins(4, 4, 8, 4)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Создаем поля ввода для каждого столбца таблицы
        for col in table.columns:
            w = self._create_input_widget(col)
            self.widgets[col.id] = w
            label_text = col.name + ("*" if col.required else "")
            form.addRow(label_text, w)

        scroll.setWidget(form_host)
        layout.addWidget(scroll, stretch=1)

        # Если переданы начальные данные (редактирование)
        if initial_data:
            self._fill_initial_data(initial_data)

        # Нижняя панель кнопок
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        if self.is_new:
            save_and_more_btn = QPushButton("Сохранить и создать ещё")
            save_and_more_btn.clicked.connect(self._on_save_and_more)
            btn_layout.addWidget(save_and_more_btn)

        save_btn = QPushButton("Сохранить")
        save_btn.setProperty("class", "Primary")
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _create_input_widget(self, col) -> QWidget:
        if col.type == T.CHOICE:
            cb = QComboBox()
            cb.setMinimumHeight(32)
            choices = col.options.get("choices") or []
            if not col.required:
                cb.addItem("— Не выбрано —", "")
            for ch in choices:
                cb.addItem(ch, ch)
            if col.default and col.default in choices:
                cb.setCurrentText(col.default)
            return cb

        if col.type == T.BOOL:
            chk = QCheckBox()
            if col.default:
                chk.setChecked(col.default in ("1", "Да", "True", "true"))
            return chk

        if col.type == T.DATE:
            de = QDateEdit()
            de.setMinimumHeight(32)
            de.setCalendarPopup(True)
            de.setDisplayFormat("dd.MM.yyyy")
            de.setDate(QDate.currentDate())
            return de

        if col.type == T.TIME:
            te = QTimeEdit()
            te.setMinimumHeight(32)
            te.setDisplayFormat("HH:mm:ss")
            te.setTime(QTime.currentTime())
            return te

        if col.type == T.DATETIME:
            dte = QDateTimeEdit()
            dte.setMinimumHeight(32)
            dte.setCalendarPopup(True)
            dte.setDisplayFormat("dd.MM.yyyy HH:mm")
            dte.setDateTime(QDateTime.currentDateTime())
            return dte

        if col.type == T.INTEGER:
            sb = QSpinBox()
            sb.setMinimumHeight(32)
            sb.setRange(-2_000_000_000, 2_000_000_000)
            if col.default:
                try:
                    sb.setValue(int(col.default))
                except ValueError:
                    pass
            return sb

        if col.type in (T.FLOAT, T.MONEY):
            dsb = QDoubleSpinBox()
            dsb.setMinimumHeight(32)
            dsb.setRange(-1_000_000_000.0, 1_000_000_000.0)
            dsb.setDecimals(2 if col.type == T.MONEY else 4)
            if col.default:
                try:
                    dsb.setValue(float(col.default))
                except ValueError:
                    pass
            return dsb

        if col.type == T.NOTE:
            te = QTextEdit()
            te.setMaximumHeight(80)
            return te

        # Обычный текст
        le = QLineEdit()
        le.setMinimumHeight(32)
        if col.default:
            le.setText(default_display(col))

        if col.options.get("autocomplete", False) or col.name.lower() in (
            "фамилия", "имя", "отчество", "название товара", "поставщик", "организация"
        ):
            try:
                vals = self.ctx.records.distinct(self.table, col.id, limit=500)
                if vals:
                    completer = QCompleter(vals, self)
                    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                    le.setCompleter(completer)
            except Exception:
                pass

        return le

    def _fill_initial_data(self, data: dict[int, Any]) -> None:
        for col in self.table.columns:
            w = self.widgets.get(col.id)
            val = data.get(col.id)
            if val is None or w is None:
                continue

            if isinstance(w, QComboBox):
                w.setCurrentText(str(val))
            elif isinstance(w, QCheckBox):
                w.setChecked(bool(val))
            elif isinstance(w, QDateEdit) and isinstance(val, (dt.date, str)):
                d = dt.date.fromisoformat(str(val)) if isinstance(val, str) else val
                w.setDate(QDate(d.year, d.month, d.day))
            elif isinstance(w, QTimeEdit) and isinstance(val, (dt.time, str)):
                t = dt.time.fromisoformat(str(val)) if isinstance(val, str) else val
                w.setTime(QTime(t.hour, t.minute, t.second))
            elif isinstance(w, QDateTimeEdit) and isinstance(val, (dt.datetime, str)):
                dt_val = dt.datetime.fromisoformat(str(val)) if isinstance(val, str) else val
                w.setDateTime(QDateTime(dt_val.year, dt_val.month, dt_val.day, dt_val.hour, dt_val.minute, dt_val.second))
            elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                if col.type == T.MONEY and isinstance(val, (int, float)):
                    w.setValue(val / 100.0)
                else:
                    w.setValue(float(val))
            elif isinstance(w, QTextEdit):
                w.setText(str(val))
            elif isinstance(w, QLineEdit):
                w.setText(T.to_edit_text(col.type, val))

    def collect_data(self) -> dict[int, Any]:
        raw: dict[int, Any] = {}
        for col in self.table.columns:
            w = self.widgets[col.id]
            if isinstance(w, QComboBox):
                raw[col.id] = w.currentData() or w.currentText()
            elif isinstance(w, QCheckBox):
                raw[col.id] = 1 if w.isChecked() else 0
            elif isinstance(w, QDateEdit):
                qdate = w.date()
                raw[col.id] = f"{qdate.year():04d}-{qdate.month():02d}-{qdate.day():02d}"
            elif isinstance(w, QTimeEdit):
                qtime = w.time()
                raw[col.id] = f"{qtime.hour():02d}:{qtime.minute():02d}:{qtime.second():02d}"
            elif isinstance(w, QDateTimeEdit):
                qdt = w.dateTime()
                raw[col.id] = f"{qdt.date().year():04d}-{qdt.date().month():02d}-{qdt.date().day():02d} " \
                             f"{qdt.time().hour():02d}:{qdt.time().minute():02d}:{qdt.time().second():02d}"
            elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                raw[col.id] = w.value()
            elif isinstance(w, QTextEdit):
                raw[col.id] = w.toPlainText()
            elif isinstance(w, QLineEdit):
                raw[col.id] = w.text().strip()
        return raw

    def _save(self) -> bool:
        data = self.collect_data()
        try:
            if self.is_new:
                self.ctx.records.insert(self.table.id, data)
            else:
                assert self.row_id is not None
                self.ctx.records.update(self.table.id, self.row_id, data)
            return True
        except WMError as exc:
            show_error(self, "Ошибка сохранения записи", str(exc))
            return False

    def _on_save(self) -> None:
        if self._save():
            self.accept()

    def _on_save_and_more(self) -> None:
        if self._save():
            self.add_another = True
            for col in self.table.columns:
                w = self.widgets[col.id]
                if isinstance(w, QLineEdit):
                    w.clear()
                elif isinstance(w, QTextEdit):
                    w.clear()
                elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                    w.setValue(0)
