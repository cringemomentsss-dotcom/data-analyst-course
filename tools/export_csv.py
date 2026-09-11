#!/usr/bin/env python3
"""
Выгрузка результата SQL-запроса в CSV — для Tableau Public.

Tableau Public не умеет подключаться к базам данных: только файлы
(.csv, .xlsx, .tsv) и Google Таблицы. Поэтому витрина считается в SQL,
выгружается этим скриптом, и Tableau визуализирует уже файл.

Запуск:
    python3 tools/export_csv.py путь/к/mart.sql путь/к/out.csv
    python3 tools/export_csv.py -c "SELECT ..." out.csv

Зависимостей нет: ходит в базу через docker compose exec psql.
"""

import os
import subprocess
import sys


def run(query, out_path):
    q = "SET search_path TO casino, public;\n" + query
    p = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres",
         "psql", "-U", "analyst", "-d", "casino",
         "-v", "ON_ERROR_STOP=1", "-q", "--csv"],
        input=q, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit("Ошибка SQL:\n" + (p.stderr.strip() or p.stdout.strip()))
    body = p.stdout
    if not body.strip():
        sys.exit("Запрос вернул пусто — выгружать нечего.")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(body)
    rows = body.count("\n") - 1
    size = os.path.getsize(out_path)
    print(f"{out_path}: {rows:,} строк, {size/1024:.0f} КБ")
    if rows == 0:
        print("  ВНИМАНИЕ: только шапка, ни одной строки данных.")


def main():
    args = sys.argv[1:]
    if len(args) == 3 and args[0] == "-c":
        run(args[1], args[2])
    elif len(args) == 2:
        sql_path, out_path = args
        if not os.path.exists(sql_path):
            sys.exit(f"Не нашёл файл запроса: {sql_path}")
        run(open(sql_path, encoding="utf-8").read(), out_path)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
