"""Типы данных столбцов: проверка, преобразование для хранения и отображения.

Формат хранения (не зависит от СУБД, пригоден и для PostgreSQL):
* text / note / choice — строка;
* integer — целое; float — вещественное;
* money — целое число копеек/тиын (без ошибок округления);
* date — 'YYYY-MM-DD'; time — 'HH:MM:SS'; datetime — 'YYYY-MM-DD HH:MM:SS'
  (ISO-формат: сравнение строк = сравнение дат, работают диапазоны и индексы);
* bool — 0 / 1.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

TEXT = "text"
INTEGER = "integer"
FLOAT = "float"
DATE = "date"
TIME = "time"
DATETIME = "datetime"
BOOL = "bool"
MONEY = "money"
NOTE = "note"
CHOICE = "choice"


@dataclass(frozen=True)
class TypeInfo:
    code: str
    label: str
    sql: str  # тип хранения


TYPES: dict[str, TypeInfo] = {
    TEXT: TypeInfo(TEXT, "Текст", "TEXT"),
    INTEGER: TypeInfo(INTEGER, "Целое число", "INTEGER"),
    FLOAT: TypeInfo(FLOAT, "Дробное число", "REAL"),
    DATE: TypeInfo(DATE, "Дата", "TEXT"),
    TIME: TypeInfo(TIME, "Время", "TEXT"),
    DATETIME: TypeInfo(DATETIME, "Дата и время", "TEXT"),
    BOOL: TypeInfo(BOOL, "Логическое (Да/Нет)", "INTEGER"),
    MONEY: TypeInfo(MONEY, "Денежное значение", "INTEGER"),
    NOTE: TypeInfo(NOTE, "Примечание", "TEXT"),
    CHOICE: TypeInfo(CHOICE, "Список значений", "TEXT"),
}

TEXTUAL = {TEXT, NOTE, CHOICE}
NUMERIC = {INTEGER, FLOAT, MONEY}
TEMPORAL = {DATE, TIME, DATETIME}

MAX_TEXT_LEN = 10_000
MAX_NOTE_LEN = 100_000

_DATE_FORMATS = (
    "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y.%m.%d",
    "%d.%m.%y", "%d/%m/%y", "%d %m %Y",
)
_TIME_FORMATS = ("%H:%M:%S", "%H:%M", "%H.%M", "%H:%M:%S.%f", "%I:%M %p", "%I:%M:%S %p")
_RU_MONTHS = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6, "июл": 7,
    "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}
_TRUE = {"1", "да", "д", "true", "t", "yes", "y", "истина", "+", "✓", "✔", "x", "х", "вкл"}
_FALSE = {"0", "нет", "н", "false", "f", "no", "n", "ложь", "-", "", "выкл"}
_EXCEL_EPOCH = dt.datetime(1899, 12, 30)
_WS_RE = re.compile(r"\s+")


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def normalize_spaces(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("ожидалось число")
    if isinstance(value, (int, Decimal)):
        return Decimal(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("недопустимое число")
        return Decimal(repr(value))
    s = str(value).strip()
    s = s.replace("\u00a0", "").replace("\u202f", "").replace(" ", "").replace("'", "")
    s = re.sub(r"(₸|тг\.?|тенге|руб\.?|р\.|₽|\$|€|usd|kzt|rub)$", "", s, flags=re.I)
    s = re.sub(r"^(₸|\$|€|₽)", "", s)
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    elif s.count(",") >= 1 and s.count(".") == 1 and s.rfind(".") > s.rfind(","):
        s = s.replace(",", "")  # 1,234.56
    elif s.count(".") >= 1 and s.count(",") == 1 and s.rfind(",") > s.rfind("."):
        s = s.replace(".", "").replace(",", ".")  # 1.234,56
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"«{value}» не является числом") from None
    if not d.is_finite():
        raise ValueError("недопустимое число")
    return d


def _parse_date(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 1 <= value < 2958466:  # серийный номер даты Excel
            return (_EXCEL_EPOCH + dt.timedelta(days=float(value))).date()
        raise ValueError("некорректная дата")
    s = normalize_spaces(str(value))
    # Отбрасываем время, если пришла дата-время
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M",
                "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    m = re.match(r"^(\d{1,2})\s+([а-яё]+)\.?\s+(\d{4})", s.lower())
    if m:
        for key, month in _RU_MONTHS.items():
            if m.group(2).startswith(key):
                return dt.date(int(m.group(3)), month, int(m.group(1)))
    raise ValueError(f"«{value}» не является датой (пример: 12.11.2026)")


def _parse_time(value: Any) -> dt.time:
    if isinstance(value, dt.datetime):
        return value.time().replace(microsecond=0)
    if isinstance(value, dt.time):
        return value.replace(microsecond=0)
    if isinstance(value, dt.timedelta):
        secs = int(value.total_seconds()) % 86400
        return dt.time(secs // 3600, secs % 3600 // 60, secs % 60)
    if isinstance(value, float) and 0 <= value < 1:  # доля суток из Excel
        secs = round(value * 86400) % 86400
        return dt.time(secs // 3600, secs % 3600 // 60, secs % 60)
    s = normalize_spaces(str(value)).upper()
    for fmt in _TIME_FORMATS:
        try:
            return dt.datetime.strptime(s, fmt).time().replace(microsecond=0)
        except ValueError:
            pass
    raise ValueError(f"«{value}» не является временем (пример: 14:30)")


def _parse_datetime(value: Any) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value.replace(microsecond=0, tzinfo=None)
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time())
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 1 <= value < 2958466:
            return (_EXCEL_EPOCH + dt.timedelta(days=float(value))).replace(microsecond=0)
        raise ValueError("некорректные дата и время")
    s = normalize_spaces(str(value)).replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M",
                "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d.%m.%y %H:%M", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return dt.datetime.strptime(s, fmt).replace(microsecond=0)
        except ValueError:
            pass
    return dt.datetime.combine(_parse_date(s), dt.time())


def parse_bool(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return 1 if value else 0
    s = str(value).strip().lower()
    if s in _TRUE:
        return 1
    if s in _FALSE:
        return 0
    raise ValueError(f"«{value}» не является логическим значением (Да/Нет)")


def to_storage(type_code: str, value: Any, options: dict | None = None) -> Any:
    """Проверяет и преобразует значение к формату хранения. Пустое → None.

    Бросает ValueError с понятным текстом при некорректном значении.
    """
    options = options or {}
    if type_code != BOOL and is_empty(value):
        return None
    if type_code in (TEXT, CHOICE):
        s = normalize_spaces(str(value) if not isinstance(value, float) or not value.is_integer()
                             else str(int(value)))
        if len(s) > MAX_TEXT_LEN:
            raise ValueError(f"текст длиннее {MAX_TEXT_LEN} символов")
        if type_code == CHOICE:
            choices = options.get("choices") or []
            if choices:
                low = s.casefold()
                for c in choices:
                    if c.casefold() == low:
                        return c
                if not options.get("allow_other"):
                    raise ValueError(f"«{s}» нет в списке: {', '.join(choices)}")
        return s
    if type_code == NOTE:
        s = str(value).strip()
        if len(s) > MAX_NOTE_LEN:
            raise ValueError(f"примечание длиннее {MAX_NOTE_LEN} символов")
        return s
    if type_code == INTEGER:
        d = _to_decimal(value)
        if d != d.to_integral_value():
            raise ValueError(f"«{value}» не является целым числом")
        i = int(d)
        if abs(i) > 2**63 - 1:
            raise ValueError("число слишком большое")
        return i
    if type_code == FLOAT:
        return float(_to_decimal(value))
    if type_code == MONEY:
        d = _to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cents = int(d * 100)
        if abs(cents) > 2**63 - 1:
            raise ValueError("сумма слишком большая")
        return cents
    if type_code == DATE:
        d = _parse_date(value)
        if not 1 <= d.year <= 9999:
            raise ValueError("год вне допустимого диапазона")
        return d.isoformat()
    if type_code == TIME:
        return _parse_time(value).strftime("%H:%M:%S")
    if type_code == DATETIME:
        return _parse_datetime(value).strftime("%Y-%m-%d %H:%M:%S")
    if type_code == BOOL:
        if is_empty(value):
            return None if value is None else 0
        return parse_bool(value)
    raise ValueError(f"неизвестный тип данных: {type_code}")


def _fmt_number(value: float, decimals: int | None = None) -> str:
    if decimals is None:
        text = f"{value:.10f}".rstrip("0").rstrip(".")
        if text in ("-0", ""):
            text = "0"
    else:
        text = f"{value:,.{decimals}f}".replace(",", " ")
    return text.replace(".", ",")


def to_display(type_code: str, stored: Any) -> str:
    """Человекочитаемое представление хранимого значения."""
    if stored is None:
        return ""
    try:
        if type_code == INTEGER:
            return str(int(stored))
        if type_code == FLOAT:
            return _fmt_number(float(stored))
        if type_code == MONEY:
            return _fmt_number(int(stored) / 100, 2)
        if type_code == DATE:
            return dt.date.fromisoformat(str(stored)).strftime("%d.%m.%Y")
        if type_code == TIME:
            t = dt.time.fromisoformat(str(stored))
            return t.strftime("%H:%M:%S" if t.second else "%H:%M")
        if type_code == DATETIME:
            d = dt.datetime.fromisoformat(str(stored))
            return d.strftime("%d.%m.%Y %H:%M:%S" if d.second else "%d.%m.%Y %H:%M")
        if type_code == BOOL:
            return "Да" if int(stored) else "Нет"
    except (ValueError, TypeError):
        return str(stored)
    return str(stored)


def to_python(type_code: str, stored: Any) -> Any:
    """Значение для экспорта в Excel (дата → date, деньги → Decimal-подобный float и т.д.)."""
    if stored is None:
        return None
    try:
        if type_code == MONEY:
            return int(stored) / 100
        if type_code == DATE:
            return dt.date.fromisoformat(str(stored))
        if type_code == TIME:
            return dt.time.fromisoformat(str(stored))
        if type_code == DATETIME:
            return dt.datetime.fromisoformat(str(stored))
        if type_code == BOOL:
            return "Да" if int(stored) else "Нет"
    except (ValueError, TypeError):
        return str(stored)
    return stored


def to_edit_text(type_code: str, stored: Any) -> str:
    """Текст для редактора ячейки (без разделителей разрядов)."""
    if stored is None:
        return ""
    if type_code == MONEY:
        return _fmt_number(int(stored) / 100, None) if int(stored) % 100 == 0 \
            else f"{int(stored) / 100:.2f}".replace(".", ",")
    return to_display(type_code, stored)


def infer_type(samples: list[Any]) -> str:
    """Определяет наиболее подходящий тип по выборке значений (для импорта)."""
    values = [v for v in samples if not is_empty(v)]
    if not values:
        return TEXT

    def all_ok(code: str) -> bool:
        for v in values:
            try:
                to_storage(code, v)
            except ValueError:
                return False
        return True

    if all(isinstance(v, dt.datetime) for v in values):
        if all(v.time() == dt.time() for v in values):
            return DATE
        return DATETIME
    if all(isinstance(v, dt.date) and not isinstance(v, dt.datetime) for v in values):
        return DATE
    if all(isinstance(v, dt.time) for v in values):
        return TIME
    if all(isinstance(v, bool) for v in values):
        return BOOL
    strings = [v for v in values if isinstance(v, str)]
    if not strings:  # только числа
        if all(isinstance(v, int) or (isinstance(v, float) and v.is_integer()) for v in values):
            return INTEGER
        return FLOAT
    if len(strings) == len(values):
        if all(re.fullmatch(r"[+-]?\d{1,15}", s.strip()) for s in strings):
            # Номера с ведущими нулями (артикулы, телефоны) оставляем текстом
            if any(s.strip().lstrip("+-").startswith("0") and len(s.strip()) > 1 for s in strings):
                return TEXT
            return INTEGER
        if all(re.fullmatch(r"[+-]?\d[\d\s\u00a0]*[.,]\d+", s.strip()) for s in strings):
            return FLOAT
        if all(re.search(r"\d", s) and re.search(r"[./-]", s) for s in strings) and all_ok(DATE):
            if any(re.search(r"\d{1,2}:\d{2}", s) for s in strings) and all_ok(DATETIME):
                return DATETIME
            return DATE
        if all(re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", s.strip()) for s in strings):
            return TIME
        if any(len(s) > 255 for s in strings):
            return NOTE
    return TEXT
