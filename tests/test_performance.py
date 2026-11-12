"""Нагрузочное тестирование на скорость работы со 100 000 записями."""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from wm.app_context import AppContext
from wm.core.security import ROLE_ADMIN
from wm.services.templates import get_templates


def test_performance_bulk_records():
    temp_dir = tempfile.mkdtemp()
    db_file = Path(temp_dir) / "perf.db"
    ctx = AppContext(db_file=db_file)
    ctx.initialize()
    ctx.session.login(ctx.users.authenticate("admin", "admin123"))

    tmpl = next(t for t in get_templates() if t.code == "warehouse")
    t_id = ctx.tables.create("Большой склад", tmpl.columns, kind="warehouse")
    table = ctx.tables.get(t_id)
    cols = {c.name: c.id for c in table.columns}

    # Генерируем 100 000 записей
    N = 100_000
    rows = []
    t0 = time.perf_counter()
    for i in range(N):
        rows.append([
            f"Фамилия_{i % 500}",
            f"Имя_{i % 100}",
            f"Отчество_{i % 100}",
            "Привёз" if i % 2 == 0 else "Забрал",
            f"Товар Кабель тип {i % 1000}",
            float(i + 1),
            "2026-11-12",
            "12:00:00",
            f"Партия #{i}",
        ])

    # Прямая массовая вставка через репозиторий для имитации импорта 100 000 строк
    with ctx.db.begin() as conn:
        from wm.db.repository import DataRepository as Repo
        from wm.services.common import now_str
        Repo.insert_bulk(conn, table.physical, [c.physical for c in table.columns], rows, now_str())

    insert_time = time.perf_counter() - t0
    print(f"\nВремя вставки {N} строк: {insert_time:.2f} сек (скорость: {N / insert_time:.0f} строк/сек)")

    # Проверяем подсчет общего количества строк
    t_count = time.perf_counter()
    cnt = ctx.records.count(table)
    count_time = time.perf_counter() - t_count
    assert cnt == N
    print(f"Подсчет 100 000 строк: {count_time * 1000:.2f} мс")

    # Проверяем мгновенную пагинацию (LIMIT 200 OFFSET 50000)
    t_page = time.perf_counter()
    page_data = ctx.records.fetch(table, limit=200, offset=50_000)
    page_time = time.perf_counter() - t_page
    assert len(page_data) == 200
    print(f"Выборка страницы из середины (строки 50 000-50 200): {page_time * 1000:.2f} мс")

    # Проверяем фильтрацию по индексированному полю
    t_search = time.perf_counter()
    found = ctx.records.fetch(table, quick="Фамилия_123", limit=200)
    search_time = time.perf_counter() - t_search
    print(f"Поиск среди 100 000 строк: {search_time * 1000:.2f} мс (найдено: {len(found)})")

    ctx.shutdown()
    assert insert_time < 10.0  # Вставка должна занимать считанные секунды
    assert page_time < 0.1     # Пагинация должна выполняться быстрее 100 мс
