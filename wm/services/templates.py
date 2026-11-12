"""Готовые шаблоны таблиц."""
from __future__ import annotations

from dataclasses import dataclass

from wm.core import types as T
from wm.services.common import ColumnSpec

OPERATIONS = ["Привёз", "Забрал"]


@dataclass
class Template:
    code: str
    title: str
    description: str
    kind: str
    columns: list[ColumnSpec]


def _c(name, type_=T.TEXT, required=False, default=None, indexed=False, width=0, **options):
    return ColumnSpec(name=name, type=type_, required=required, default=default,
                      indexed=indexed, width=width, options=options)


def warehouse_columns() -> list[ColumnSpec]:
    return [
        _c("Фамилия", required=True, indexed=True, width=140, autocomplete=True),
        _c("Имя", indexed=False, width=120, autocomplete=True),
        _c("Отчество", width=140, autocomplete=True),
        _c("Тип операции", T.CHOICE, required=True, indexed=True, width=120,
           choices=list(OPERATIONS)),
        _c("Название товара", required=True, indexed=True, width=220, autocomplete=True),
        _c("Количество", T.FLOAT, required=True, width=100),
        _c("Дата", T.DATE, required=True, default="{today}", indexed=True, width=110),
        _c("Время", T.TIME, default="{time}", width=80),
        _c("Комментарий", T.NOTE, width=260),
    ]


def get_templates() -> list[Template]:
    return [
        Template("warehouse", "Складской учёт",
                 "Приход и выдача товаров: ФИО, операция, товар, количество, дата и время.",
                 "warehouse", warehouse_columns()),
        Template("visits", "Журнал посещений",
                 "Учёт посетителей: ФИО, организация, цель, время прихода и ухода.", "generic", [
                     _c("ФИО", required=True, indexed=True, width=220, autocomplete=True),
                     _c("Организация", width=180, autocomplete=True),
                     _c("Цель визита", width=200),
                     _c("Дата", T.DATE, required=True, default="{today}", indexed=True),
                     _c("Время прихода", T.TIME, default="{time}"),
                     _c("Время ухода", T.TIME),
                     _c("Примечание", T.NOTE, width=220),
                 ]),
        Template("goods", "Учёт товаров",
                 "Справочник товаров: артикул, название, категория, остаток, цена.", "generic", [
                     _c("Артикул", indexed=True, width=110),
                     _c("Название товара", required=True, indexed=True, width=240,
                        autocomplete=True),
                     _c("Категория", width=140, autocomplete=True),
                     _c("Единица измерения", T.CHOICE, default="шт", width=90,
                        choices=["шт", "кг", "л", "м", "упак", "компл"], allow_other=True),
                     _c("Остаток", T.FLOAT, default="0", width=90),
                     _c("Цена", T.MONEY, width=110),
                     _c("Поставщик", width=160, autocomplete=True),
                     _c("Активен", T.BOOL, default="Да", width=70),
                 ]),
        Template("operations", "Журнал операций",
                 "Произвольные операции: дата/время, тип, описание, сумма, ответственный.",
                 "generic", [
                     _c("Дата и время", T.DATETIME, required=True, default="{now}",
                        indexed=True, width=150),
                     _c("Тип операции", indexed=True, width=140, autocomplete=True),
                     _c("Описание", width=280),
                     _c("Сумма", T.MONEY, width=110),
                     _c("Ответственный", width=160, autocomplete=True),
                     _c("Выполнено", T.BOOL, default="Нет", width=80),
                 ]),
        Template("blank", "Пустая таблица",
                 "Начните с одного столбца и настройте структуру самостоятельно.", "generic", [
                     _c("Название", width=200),
                 ]),
    ]
