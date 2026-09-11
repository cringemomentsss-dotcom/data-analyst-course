#!/usr/bin/env python3
"""
Проверка SQL-решений: сравнивает результат твоего запроса с эталонным.

Сравнивается РЕЗУЛЬТАТ, а не текст запроса, — свой способ решения тоже
засчитывается. Числа с плавающей точкой сравниваются с допуском.

Зависимостей нет: ходит в базу через docker compose exec psql.

Формат файлов — SQL с маркерами:

    -- TASK: 1.1
    SELECT ...;

    -- TASK: 1.2
    SELECT ...;

Запуск:
    python3 tools/check_sql.py путь/otvety.sql путь/.etalon.sql
    python3 tools/check_sql.py путь/otvety.sql путь/.etalon.sql 2.3    # одну задачу
"""

import re
import subprocess
import sys
from decimal import Decimal, InvalidOperation

TOL = 0.011          # допуск на округление
SEP = "\x01"


def run_sql(query):
    """Выполнить запрос и вернуть (columns, rows) либо бросить RuntimeError."""
    q = "SET search_path TO casino, public;\n" + query
    p = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres",
         "psql", "-U", "analyst", "-d", "casino", "-v", "ON_ERROR_STOP=1", "-q",
         "--no-align", "--field-separator", SEP, "--pset", "footer=off"],
        input=q, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    lines = [l for l in p.stdout.splitlines() if l != ""]
    # psql печатает результат SET первой строкой только при ошибке; здесь его нет
    if not lines:
        return [], []
    header, *body = lines
    return header.split(SEP), [tuple(l.split(SEP)) for l in body]


def norm_cell(x):
    if x == "":
        return None
    try:
        d = Decimal(x)
        return ("num", d)
    except InvalidOperation:
        return ("str", x.strip())


def norm_rows(rows):
    return [tuple(norm_cell(c) for c in r) for r in rows]


def cells_equal(a, b):
    if a is None or b is None:
        return a is b
    if a[0] != b[0]:
        return False
    if a[0] == "num":
        return abs(a[1] - b[1]) <= Decimal(str(TOL))
    return a[1] == b[1]


def rows_equal(a, b):
    if len(a) != len(b):
        return False
    return all(len(x) == len(y) and all(cells_equal(i, j) for i, j in zip(x, y))
               for x, y in zip(a, b))


def as_multiset(rows):
    return sorted(rows, key=lambda r: [("" if c is None else str(c)) for c in r])


def parse(path):
    text = open(path, encoding="utf-8").read()
    blocks, cur, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^\s*--\s*TASK:\s*(\S+)", line)
        if m:
            if cur:
                blocks[cur] = "\n".join(buf).strip()
            cur, buf = m.group(1), []
        elif cur is not None:
            buf.append(line)
    if cur:
        blocks[cur] = "\n".join(buf).strip()
    return {k: v for k, v in blocks.items() if v.strip()}


def strip_sql_comments(s):
    return "\n".join(l for l in s.splitlines() if not l.strip().startswith("--")).strip()


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    mine = parse(sys.argv[1])
    ref = parse(sys.argv[2])
    only = sys.argv[3] if len(sys.argv) > 3 else None

    ids = [i for i in ref if not only or i == only]
    ok = fail = skip = 0

    for tid in ids:
        my_sql = strip_sql_comments(mine.get(tid, ""))
        if not my_sql:
            print(f"  {tid:<6} — не решена")
            skip += 1
            continue
        try:
            my_cols, my_rows = run_sql(my_sql)
        except RuntimeError as e:
            print(f"✗ {tid:<6} ОШИБКА SQL")
            first = str(e).splitlines()[0] if str(e) else "неизвестная ошибка"
            print(f"          {first}")
            fail += 1
            continue
        ref_cols, ref_rows = run_sql(ref[tid])
        a, b = norm_rows(my_rows), norm_rows(ref_rows)

        if rows_equal(a, b):
            if my_cols != ref_cols:
                print(f"✓ {tid:<6} значения верны, но названия столбцов другие")
                print(f"          у тебя:    {', '.join(my_cols)}")
                print(f"          ожидается: {', '.join(ref_cols)}")
            else:
                print(f"✓ {tid:<6} верно")
            ok += 1
        elif rows_equal(as_multiset(a), as_multiset(b)):
            print(f"~ {tid:<6} строки те же, но порядок другой — проверь ORDER BY")
            fail += 1
        else:
            print(f"✗ {tid:<6} неверно")
            print(f"          у тебя: {len(a)} строк, ожидается: {len(b)}")
            if a and b and len(a[0]) != len(b[0]):
                print(f"          столбцов: {len(a[0])} против {len(b[0])}")
            elif b:
                for i, (x, y) in enumerate(zip(a, b)):
                    if not (len(x) == len(y) and all(cells_equal(p, q) for p, q in zip(x, y))):
                        print(f"          первое расхождение в строке {i+1}:")
                        print(f"            у тебя:    {my_rows[i]}")
                        print(f"            ожидается: {ref_rows[i]}")
                        break
            fail += 1

    total = ok + fail + skip
    print(f"\nРешено верно: {ok} из {total}" + (f", не решено: {skip}" if skip else ""))
    return 0 if fail == 0 and skip == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
