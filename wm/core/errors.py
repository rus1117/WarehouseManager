"""Иерархия исключений приложения. Все сообщения — для конечного пользователя."""


class WMError(Exception):
    """Базовое исключение приложения."""


class ValidationError(WMError):
    """Некорректные входные данные."""


class PermissionDenied(WMError):
    """Недостаточно прав для операции."""


class NotFound(WMError):
    """Объект не найден."""


class StorageError(WMError):
    """Ошибка записи / чтения хранилища."""


class DiskFullError(StorageError):
    """Недостаточно места на диске."""


class IncompatibleDatabase(WMError):
    """База создана более новой версией программы или повреждена."""


class OperationCancelled(WMError):
    """Операция отменена пользователем."""


def translate_os_error(exc: BaseException) -> WMError:
    """Преобразует системные ошибки в понятные пользователю сообщения."""
    import errno
    import sqlite3

    text = str(exc)
    low = text.lower()
    if isinstance(exc, WMError):
        return exc
    if "disk is full" in low or "database or disk is full" in low:
        return DiskFullError("Недостаточно места на диске. Освободите место и повторите операцию.")
    if isinstance(exc, OSError):
        if exc.errno == errno.ENOSPC:
            return DiskFullError("Недостаточно места на диске. Освободите место и повторите операцию.")
        if isinstance(exc, PermissionError) or exc.errno in (errno.EACCES, errno.EPERM):
            return StorageError(
                f"Нет доступа к файлу: {getattr(exc, 'filename', '') or ''}\n"
                "Возможно, файл открыт в другой программе или защищён от записи."
            )
        if isinstance(exc, FileNotFoundError):
            return StorageError(f"Файл не найден: {getattr(exc, 'filename', '') or ''}")
        return StorageError(f"Ошибка файловой системы: {text}")
    if isinstance(exc, sqlite3.DatabaseError) or "sqlite" in type(exc).__module__.lower() \
            or "database" in low:
        if "locked" in low:
            return StorageError("База данных занята другим процессом. Повторите попытку.")
        if "malformed" in low or "not a database" in low:
            return StorageError("Файл базы данных повреждён или не является базой данных.")
        return StorageError(f"Ошибка базы данных: {text}")
    return WMError(text)
