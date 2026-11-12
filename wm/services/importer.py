"""Импорт данных из XLSX / XLSM / CSV.

Безопасность:
* файл открывается только на чтение и никогда не изменяется;
* макросы XLSM не выполняются (openpyxl не исполняет VBA, keep_vba=False);
* формулы не вычисляются — читаются сохранённые значения (data_only=True);
* внешние ссылки не загружаются (keep_links=False);
* проверяются сигнатура и размер файла.

Импорт транзакционный: при отмене или критической ошибке база не изменяется.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterator

from wm.core import types as T
from wm.core.errors import OperationCancelled, ValidationError, WMError, translate_os_error
from wm.core.security import P_IMPORT
from wm.db.repository import DataRepository as Repo
from wm.services.common import ColumnSpec, TableInfo, log_change, now_str, touch_table
from wm.services.records import resolve_default

if TYPE_CHECKING:
    from wm.app_context import AppContext

log = logging.getLogger(__name__)

MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1 ГБ
BATCH = 2000
PREVIEW_ROWS = 200
SUPPORTED = {".xlsx", ".xlsm", ".csv", ".txt"}

DUP_ALL = "all"
DUP_SKIP = "skip_exact"
DUP_WARN = "warn"

ERR_SKIP_ROW = "skip_row"
ERR_EMPTY_CELL = "empty_cell"

ProgressCb = Callable[[int, int, str], None]
CancelCb = Callable[[], bool]


@dataclass
class SheetInfo:
    name: str
    rows: int
    cols: int


@dataclass
class FileInfo:
    path: Path
    kind: str  # xlsx | csv
    sheets: list[SheetInfo]
    encoding: str = "utf-8"
    delimiter: str = ","


@dataclass
class ImportColumn:
    source_index: int            # номер столбца в файле (0..)
    source_name: str
    target_col_id: int | None = None   # существующий столбец (импорт в имеющуюся таблицу)
    new_spec: ColumnSpec | None = None  # новый столбец (импорт в новую таблицу)
    skip: bool = False


@dataclass
class ImportPlan:
    path: Path
    sheet: str
    header_row: int = 1                  # 1-based; 0 — без заголовков
    columns: list[ImportColumn] = field(default_factory=list)
    target_table_id: int | None = None
    new_table_name: str = ""
    new_table_kind: str = "generic"
    new_table_category_id: int | None = None
    duplicate_mode: str = DUP_ALL
    error_mode: str = ERR_SKIP_ROW
    skip_empty_rows: bool = True
    apply_defaults: bool = False


@dataclass
class RowError:
    row: int        # номер строки в исходном файле
    column: str
    message: str
    value: str = ""


@dataclass
class ImportResult:
    total_rows: int = 0
    imported: int = 0
    error_rows: int = 0
    skipped_duplicates: int = 0
    possible_duplicates: int = 0
    empty_rows: int = 0
    errors: list[RowError] = field(default_factory=list)
    duplicate_rows: list[int] = field(default_factory=list)
    table_id: int | None = None
    dry_run: bool = False


# ── чтение файлов ──────────────────────────────────────────────────────
def _check_file(path: Path) -> str:
    if not path.exists():
        raise ValidationError(f"Файл не найден: {path}")
    ext = path.suffix.lower()
    if ext == ".xls":
        raise ValidationError("Старый формат XLS не поддерживается. Откройте файл в Excel "
                              "и сохраните как «Книга Excel (*.xlsx)».")
    if ext not in SUPPORTED:
        raise ValidationError("Поддерживаются файлы XLSX, XLSM и CSV.")
    size = path.stat().st_size
    if size == 0:
        raise ValidationError("Файл пустой.")
    if size > MAX_FILE_SIZE:
        raise ValidationError("Файл слишком большой (более 1 ГБ).")
    with open(path, "rb") as fh:
        head = fh.read(8)
    if ext in (".xlsx", ".xlsm"):
        if head[:4] != b"PK\x03\x04":
            raise ValidationError("Файл повреждён или не является книгой Excel (XLSX/XLSM).")
        return "xlsx"
    if head[:4] == b"PK\x03\x04" or b"\x00" in head[:4]:
        raise ValidationError("Файл не похож на текстовый CSV.")
    return "csv"


def _detect_csv(path: Path) -> tuple[str, str]:
    with open(path, "rb") as fh:
        raw = fh.read(256 * 1024)
    encoding = "utf-8-sig"
    for enc in ("utf-8-sig", "cp1251", "utf-16"):
        try:
            sample = raw.decode(enc)
            # отсечённый в середине многобайтный символ — не ошибка кодировки
            encoding = enc
            break
        except UnicodeDecodeError as exc:
            if enc == "utf-8-sig" and exc.start > len(raw) - 4:
                sample = raw[:exc.start].decode(enc)
                encoding = enc
                break
            continue
    else:
        sample = raw.decode("cp1251", errors="replace")
        encoding = "cp1251"
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        encoding = "utf-16"
        sample = raw.decode("utf-16", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(sample[:50_000], delimiters=";,\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        first = sample.splitlines()[0] if sample else ""
        delimiter = max(";,\t|", key=first.count) if first else ","
    return encoding, delimiter


def analyze(path: str | Path) -> FileInfo:
    path = Path(path)
    try:
        kind = _check_file(path)
        if kind == "xlsx":
            wb = _open_wb(path)
            try:
                sheets = []
                for ws in wb.worksheets:
                    sheets.append(SheetInfo(ws.title, ws.max_row or 0, ws.max_column or 0))
            finally:
                wb.close()
            if not sheets:
                raise ValidationError("В книге нет листов с данными.")
            return FileInfo(path, "xlsx", sheets)
        enc, delim = _detect_csv(path)
        with open(path, "r", encoding=enc, newline="", errors="replace") as fh:
            rows = sum(1 for _ in fh)
        return FileInfo(path, "csv", [SheetInfo(path.stem, rows, 0)], enc, delim)
    except WMError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("Ошибка анализа файла")
        if isinstance(exc, OSError):
            raise translate_os_error(exc) from exc
        raise ValidationError(f"Не удаётся прочитать файл: {exc}") from exc


def _open_wb(path: Path):
    import warnings

    import openpyxl
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # Чтение в память — файл на диске не блокируется и не изменяется.
        data = path.read_bytes()
        return openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True,
                                      keep_vba=False, keep_links=False)


def iter_rows(info: FileInfo, sheet: str) -> Iterator[list[Any]]:
    """Все строки листа (включая заголовок) как списки значений."""
    if info.kind == "xlsx":
        wb = _open_wb(info.path)
        try:
            if sheet not in wb.sheetnames:
                raise ValidationError(f"Лист «{sheet}» не найден.")
            ws = wb[sheet]
            for row in ws.iter_rows(values_only=True):
                yield list(row)
        finally:
            wb.close()
    else:
        with open(info.path, "r", encoding=info.encoding, newline="", errors="replace") as fh:
            reader = csv.reader(fh, delimiter=info.delimiter)
            for row in reader:
                yield list(row)


def _cell_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, dt.datetime):
        return v.strftime("%d.%m.%Y %H:%M") if v.time() != dt.time() else v.strftime("%d.%m.%Y")
    if isinstance(v, dt.date):
        return v.strftime("%d.%m.%Y")
    if isinstance(v, dt.time):
        return v.strftime("%H:%M")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def preview(info: FileInfo, sheet: str, header_row: int = 1,
            limit: int = PREVIEW_ROWS) -> tuple[list[str], list[list[Any]]]:
    """Заголовки и первые строки данных."""
    headers: list[str] = []
    rows: list[list[Any]] = []
    for idx, row in enumerate(iter_rows(info, sheet), 1):
        if header_row and idx < header_row:
            continue
        if header_row and idx == header_row:
            headers = [_cell_text(v).strip() for v in row]
            continue
        rows.append(row)
        if len(rows) >= limit:
            break
    width = max([len(headers)] + [len(r) for r in rows] or [0])
    # убираем полностью пустые хвостовые столбцы
    while width > 0 and (len(headers) < width or not headers[width - 1]) and all(
            len(r) < width or T.is_empty(r[width - 1]) for r in rows):
        width -= 1
    headers = (headers + [""] * width)[:width]
    seen: dict[str, int] = {}
    for i, h in enumerate(headers):
        h = T.normalize_spaces(h) or f"Столбец {i + 1}"
        key = h.casefold()
        if key in seen:
            seen[key] += 1
            h = f"{h} ({seen[key]})"
        else:
            seen[key] = 1
        headers[i] = h[:200]
    rows = [(list(r) + [None] * width)[:width] for r in rows]
    return headers, rows


def suggest_columns(headers: list[str], rows: list[list[Any]],
                    table: TableInfo | None = None) -> list[ImportColumn]:
    """Автоматическое сопоставление / определение типов."""
    result = []
    for i, h in enumerate(headers):
        samples = [r[i] for r in rows if i < len(r)]
        ic = ImportColumn(source_index=i, source_name=h)
        if table is not None:
            col = table.column_by_name(h)
            if col is None:
                low = h.casefold().replace("ё", "е")
                for c in table.columns:
                    if c.name.casefold().replace("ё", "е") in low or \
                            low in c.name.casefold().replace("ё", "е"):
                        col = c
                        break
            ic.target_col_id = col.id if col else None
            ic.skip = col is None
        else:
            ic.new_spec = ColumnSpec(name=h, type=T.infer_type(samples))
        result.append(ic)
    return result


# ── сервис ─────────────────────────────────────────────────────────────
class ImportService:
    def __init__(self, ctx: "AppContext") -> None:
        self.ctx = ctx

    analyze = staticmethod(analyze)
    preview = staticmethod(preview)
    suggest_columns = staticmethod(suggest_columns)

    def _targets(self, plan: ImportPlan, table: TableInfo | None):
        """[(индекс в файле, ColumnInfo|ColumnSpec-подобный)]."""
        active = [c for c in plan.columns if not c.skip]
        if not active:
            raise ValidationError("Не выбрано ни одного столбца для импорта.")
        if table is not None:
            seen = set()
            out = []
            for c in active:
                if c.target_col_id is None:
                    continue
                if c.target_col_id in seen:
                    col = table.column(c.target_col_id)
                    raise ValidationError(f"Столбец таблицы «{col.name}» сопоставлен дважды.")
                seen.add(c.target_col_id)
                out.append((c.source_index, table.column(c.target_col_id)))
            if not out:
                raise ValidationError("Не сопоставлено ни одного столбца.")
            return out
        return [(c.source_index, c.new_spec) for c in active]

    def run(self, plan: ImportPlan, progress: ProgressCb | None = None,
            cancelled: CancelCb | None = None, dry_run: bool = False) -> ImportResult:
        """Проверка (dry_run=True) или импорт. Весь импорт — одна транзакция."""
        self.ctx.session.require(P_IMPORT)
        progress = progress or (lambda *a: None)
        cancelled = cancelled or (lambda: False)
        info = analyze(plan.path)
        total_est = next((s.rows for s in info.sheets if s.name == plan.sheet), 0)
        result = ImportResult(dry_run=dry_run)

        table: TableInfo | None = None
        if plan.target_table_id is not None:
            table = self.ctx.tables.get(plan.target_table_id)
        else:
            if not dry_run:
                self.ctx.tables._check_name(plan.new_table_name)
            from wm.services.tables import validate_specs
            validate_specs([c.new_spec for c in plan.columns if not c.skip])

        targets = self._targets(plan, table)
        try:
            if dry_run:
                self._process(plan, info, table, targets, None, result, progress, cancelled,
                              total_est)
            else:
                with self.ctx.db.session() as s:
                    if table is None:
                        specs = [spec for _, spec in targets]
                        new_id = self.ctx.tables._create_in_session(
                            s, self.ctx.tables._check_name(plan.new_table_name), specs,
                            plan.new_table_kind, plan.new_table_category_id,
                            f"Импортировано из {plan.path.name}")
                        s.flush()
                        s.expire_all()
                        from wm.db.models import UserTable
                        from wm.services.tables import _to_info
                        table = _to_info(s.get(UserTable, new_id))
                        targets = [(idx, table.columns[i]) for i, (idx, _) in enumerate(targets)]
                    conn = s.connection()
                    self._process(plan, info, table, targets, conn, result, progress, cancelled,
                                  total_est)
                    if cancelled():
                        raise OperationCancelled("Импорт отменён. База данных не изменена.")
                    touch_table(conn, table.id)
                    log_change(conn, self.ctx.session.username, "import", table.id, details={
                        "file": plan.path.name, "sheet": plan.sheet, "imported": result.imported,
                        "errors": result.error_rows})
                    result.table_id = table.id
        except (WMError, OperationCancelled):
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("Критическая ошибка импорта")
            raise translate_os_error(exc) from exc
        return result

    def _process(self, plan, info, table, targets, conn, result: ImportResult, progress,
                 cancelled, total_est) -> None:
        existing_hashes: set[int] = set()
        check_dups = plan.duplicate_mode in (DUP_SKIP, DUP_WARN)
        is_existing_table = plan.target_table_id is not None
        if check_dups and is_existing_table and table is not None:
            from wm.db.engine import Database  # noqa: F401
            with self.ctx.db.connect() as rconn:
                cols = [c.physical for _, c in targets]
                existing_hashes = {hash(t) for t in Repo.all_hashes(rconn, table.physical, cols)}
        file_hashes: set[int] = set()
        target_cols = [c for _, c in targets]
        batch: list[list[Any]] = []
        phys = [c.physical for c in target_cols] if conn is not None else []
        now = now_str()
        data_index = 0

        def flush():
            if conn is not None and batch:
                if len(target_cols) < len(table.columns) and plan.apply_defaults:
                    pass
                Repo.insert_bulk(conn, table.physical, phys + extra_phys,
                                 [row + extra_vals for row in batch], now)
            batch.clear()

        # Столбцы таблицы, не участвующие в импорте: значения по умолчанию (по желанию)
        extra_phys: list[str] = []
        extra_vals: list[Any] = []
        if conn is not None and table is not None and plan.apply_defaults:
            used = {c.id for c in target_cols}
            for c in table.columns:
                if c.id not in used and c.default:
                    extra_phys.append(c.physical)
                    extra_vals.append(resolve_default(c))

        for line_no, row in enumerate(iter_rows(info, plan.sheet), 1):
            if plan.header_row and line_no <= plan.header_row:
                continue
            data_index += 1
            if data_index % 500 == 0:
                if cancelled():
                    raise OperationCancelled("Импорт отменён. База данных не изменена.")
                progress(line_no, total_est, f"Обработано строк: {data_index}")
            cells = [row[idx] if idx < len(row) else None for idx, _ in targets]
            if plan.skip_empty_rows and all(T.is_empty(v) for v in cells):
                result.empty_rows += 1
                continue
            result.total_rows += 1
            values: list[Any] = []
            row_errors: list[RowError] = []
            for (idx, col), raw in zip(targets, cells):
                name = col.name
                ctype = col.type
                opts = col.options or {}
                try:
                    v = T.to_storage(ctype, raw, opts)
                    if v is None and getattr(col, "required", False):
                        raise ValueError("обязательное поле не заполнено")
                except ValueError as exc:
                    row_errors.append(RowError(line_no, name, str(exc), _cell_text(raw)[:100]))
                    v = None
                values.append(v)
            if row_errors:
                result.errors.extend(row_errors[:5])
                if plan.error_mode == ERR_SKIP_ROW or any(
                        getattr(c, "required", False) and v is None
                        for c, v in zip(target_cols, values)):
                    result.error_rows += 1
                    continue
                result.error_rows += 1
            if check_dups:
                h = hash(tuple(values))
                if h in existing_hashes or h in file_hashes:
                    if plan.duplicate_mode == DUP_SKIP:
                        result.skipped_duplicates += 1
                        continue
                    result.possible_duplicates += 1
                    if len(result.duplicate_rows) < 10_000:
                        result.duplicate_rows.append(line_no)
                file_hashes.add(h)
            result.imported += 1
            if conn is not None:
                batch.append(values)
                if len(batch) >= BATCH:
                    flush()
        flush()
        if len(result.errors) > 100_000:
            result.errors = result.errors[:100_000]
        progress(total_est, total_est, "Готово")
