"""Экспорт в XLSX и CSV. Данные приложения при экспорте не изменяются.

* Запись идёт во временный файл, затем атомарно переименовывается — при сбое
  или нехватке места не остаётся «полузаписанного» файла.
* Защита от CSV/Excel-инъекций: строки, начинающиеся с = + - @, записываются как текст.
"""
from __future__ import annotations

import csv
import logging
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Sequence

from wm.core import types as T
from wm.core.errors import OperationCancelled, ValidationError, WMError, translate_os_error, \
    DiskFullError
from wm.core.security import P_EXPORT
from wm.db.repository import Condition, DataRepository as Repo, build_where
from wm.services.common import TableInfo, log_change

if TYPE_CHECKING:
    from wm.app_context import AppContext

log = logging.getLogger(__name__)
EXCEL_MAX_ROWS = 1_048_575
ProgressCb = Callable[[int, int, str], None]
CancelCb = Callable[[], bool]

NUMBER_FORMATS = {
    T.DATE: "DD.MM.YYYY",
    T.TIME: "HH:MM",
    T.DATETIME: "DD.MM.YYYY HH:MM",
    T.MONEY: "#,##0.00",
    T.INTEGER: "0",
}
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


@dataclass
class ExportSource:
    table: TableInfo
    conditions: Sequence[Condition] = ()
    quick: str = ""
    ids: Sequence[int] | None = None       # только выбранные строки
    sort_col: int | None = None
    desc: bool = False
    match_all: bool = True


def safe_sheet_title(name: str, used: set[str]) -> str:
    title = re.sub(r"[\[\]\*\?/\\:]", "_", name).strip("'") or "Лист"
    title = title[:31]
    base, n = title, 2
    while title.casefold() in used:
        suffix = f" ({n})"
        title = base[:31 - len(suffix)] + suffix
        n += 1
    used.add(title.casefold())
    return title


def safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "export"


def _neutralize(s: Any) -> Any:
    if isinstance(s, str) and s.startswith(_FORMULA_START) \
            and not re.fullmatch(r"[+-]?[\d\s]+([.,]\d+)?", s):
        return "'" + s
    return s


class ExportService:
    def __init__(self, ctx: "AppContext") -> None:
        self.ctx = ctx

    def _count(self, src: ExportSource) -> int:
        if src.ids is not None:
            return len(src.ids)
        where, params = self._where(src)
        with self.ctx.db.connect() as conn:
            return Repo.count(conn, src.table.physical, where, params)

    @staticmethod
    def _where(src: ExportSource):
        quick_cols = [c.physical for c in src.table.columns] if src.quick.strip() else []
        return build_where(list(src.conditions), (src.quick, quick_cols) if quick_cols else None,
                           src.match_all)

    def _batches(self, src: ExportSource):
        cols = [c.physical for c in src.table.columns]
        with self.ctx.db.connect() as conn:
            if src.ids is not None:
                ids = list(src.ids)
                for i in range(0, len(ids), 5000):
                    yield Repo.get_rows(conn, src.table.physical, cols, ids[i:i + 5000])
                return
            where, params = self._where(src)
            order = src.table.column(src.sort_col).physical if src.sort_col else None
            yield from Repo.iter_select(conn, src.table.physical, cols, where, params, order,
                                        src.desc)

    @staticmethod
    def _check_space(path: Path, estimate: int) -> None:
        try:
            free = shutil.disk_usage(path.parent).free
        except OSError:
            return
        if free < estimate:
            raise DiskFullError(
                f"Недостаточно места на диске для экспорта (нужно примерно "
                f"{estimate // 1_048_576 + 1} МБ).")

    def export(self, sources: Sequence[ExportSource], path: str | Path, fmt: str = "xlsx",
               progress: ProgressCb | None = None, cancelled: CancelCb | None = None) -> list[Path]:
        """Экспорт одной или нескольких таблиц.

        XLSX: каждая таблица — отдельный лист одной книги.
        CSV: один файл на таблицу (при нескольких — имя_таблицы.csv рядом с указанным).
        """
        self.ctx.session.require(P_EXPORT)
        if not sources:
            raise ValidationError("Нет данных для экспорта.")
        path = Path(path)
        fmt = fmt.lower()
        if fmt not in ("xlsx", "csv"):
            raise ValidationError("Поддерживаются форматы XLSX и CSV.")
        progress = progress or (lambda *a: None)
        cancelled = cancelled or (lambda: False)
        totals = [self._count(s) for s in sources]
        grand = sum(totals) or 1
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._check_space(path, grand * 200 + 1_000_000)
            if fmt == "xlsx":
                if path.suffix.lower() != ".xlsx":
                    path = path.with_suffix(".xlsx")
                out = [self._xlsx(sources, path, grand, progress, cancelled)]
            else:
                out = self._csv(sources, path, grand, progress, cancelled)
        except (WMError, OperationCancelled):
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("Ошибка экспорта")
            raise translate_os_error(exc) from exc
        with self.ctx.db.begin() as conn:
            for s, n in zip(sources, totals):
                log_change(conn, self.ctx.session.username, "export", s.table.id,
                           details={"file": str(out[0].name), "rows": n, "format": fmt})
        return out

    def _xlsx(self, sources, path: Path, grand: int, progress, cancelled) -> Path:
        from openpyxl import Workbook
        from openpyxl.cell import WriteOnlyCell
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        tmp = path.with_name(path.name + ".tmp")
        wb = Workbook(write_only=True)
        used: set[str] = set()
        done = 0
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="2F5BEA")
        header_align = Alignment(vertical="center", wrap_text=True)
        try:
            for src in sources:
                cols = src.table.columns
                part = 1

                def new_sheet():
                    title = src.table.name if part == 1 else f"{src.table.name} ч.{part}"
                    ws = wb.create_sheet(safe_sheet_title(title, used))
                    for i, c in enumerate(cols, 1):
                        width = (c.width / 7) if c.width else max(10, min(len(c.name) + 4, 40))
                        ws.column_dimensions[get_column_letter(i)].width = round(width, 1)
                    ws.freeze_panes = "A2"
                    header = []
                    for c in cols:
                        cell = WriteOnlyCell(ws, value=c.name)
                        cell.font, cell.fill, cell.alignment = header_font, header_fill, header_align
                        header.append(cell)
                    ws.append(header)
                    return ws

                ws = new_sheet()
                rows_in_sheet = 0
                for batch in self._batches(src):
                    if cancelled():
                        raise OperationCancelled("Экспорт отменён.")
                    for r in batch:
                        if rows_in_sheet >= EXCEL_MAX_ROWS:
                            if cols:
                                ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{rows_in_sheet + 1}"
                            part += 1
                            ws = new_sheet()
                            rows_in_sheet = 0
                        out = []
                        for c, v in zip(cols, r[1:]):
                            val = T.to_python(c.type, v)
                            cell = WriteOnlyCell(ws, value=val)
                            if isinstance(val, str):
                                cell.data_type = "s"  # никогда не формула
                            fmt = NUMBER_FORMATS.get(c.type)
                            if fmt and val is not None and not isinstance(val, str):
                                cell.number_format = fmt
                            out.append(cell)
                        ws.append(out)
                        rows_in_sheet += 1
                    done += len(batch)
                    progress(done, grand, f"Экспортировано строк: {done}")
                if cols:
                    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{rows_in_sheet + 1}"
            wb.save(tmp)
            os.replace(tmp, path)
        except BaseException:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            raise
        return path

    def _csv(self, sources, path: Path, grand: int, progress, cancelled) -> list[Path]:
        outputs: list[Path] = []
        done = 0
        for src in sources:
            if len(sources) == 1:
                target = path if path.suffix.lower() == ".csv" else path.with_suffix(".csv")
            else:
                stem = path.stem if path.suffix else path.name
                target = path.parent / f"{safe_filename(stem)}_{safe_filename(src.table.name)}.csv"
            tmp = target.with_name(target.name + ".tmp")
            try:
                with open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
                    writer = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL)
                    writer.writerow([_neutralize(c.name) for c in src.table.columns])
                    for batch in self._batches(src):
                        if cancelled():
                            raise OperationCancelled("Экспорт отменён.")
                        writer.writerows(
                            [[_neutralize(T.to_display(c.type, v))
                              for c, v in zip(src.table.columns, r[1:])] for r in batch])
                        done += len(batch)
                        progress(done, grand, f"Экспортировано строк: {done}")
                os.replace(tmp, target)
            except BaseException:
                try:
                    if tmp.exists():
                        tmp.unlink()
                except OSError:
                    pass
                raise
            outputs.append(target)
        return outputs
