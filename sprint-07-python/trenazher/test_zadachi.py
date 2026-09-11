"""
Проверка решений тренажёра спринта 7.

Запуск из корня курса:   make test SPRINT=07
Или напрямую:            python3 -m pytest sprint-07-python/trenazher -q
Одну задачу:             python3 -m pytest sprint-07-python/trenazher -q -k parse_price
"""

import os
from datetime import date, timedelta

import pytest

import zadachi as z

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixture.csv")


# --- 1. parse_price ---------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("1400", 1400.0),
    ("1400,00", 1400.0),
    ("900 р.", 900.0),
    ("1 400", 1400.0),
    ("  2100  ", 2100.0),
    ("1260,50", 1260.5),
    ("", None),
    (None, None),
    ("мусор", None),
])
def test_parse_price(raw, expected):
    assert z.parse_price(raw) == expected


# --- 2. normalize_name -----------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("Иван Петров", "иван петров"),
    ("  Иван   Петров ", "иван петров"),
    ("ТИМУР АСКЕРОВ", "тимур аскеров"),
    ("Заречная ", "заречная"),
    (None, None),
])
def test_normalize_name(raw, expected):
    assert z.normalize_name(raw) == expected


# --- 3. parse_date ---------------------------------------------------------

def test_parse_date():
    assert z.parse_date("01.03.2026") == (2026, 3, 1)
    assert z.parse_date("2026-03-01") == (2026, 3, 1)
    assert z.parse_date("31.12.2025") == (2025, 12, 31)


# --- 4. count_by -----------------------------------------------------------

RECORDS = [
    {"city": "Тбилиси", "amount": 100},
    {"city": "Тбилиси", "amount": 250},
    {"city": "Батуми", "amount": 70},
    {"city": None, "amount": 30},
    {"city": "Батуми", "amount": None},
]


def test_count_by():
    assert z.count_by(RECORDS, "city") == {"Тбилиси": 2, "Батуми": 2, None: 1}
    assert z.count_by([], "city") == {}


# --- 5. sum_by -------------------------------------------------------------

def test_sum_by():
    assert z.sum_by(RECORDS, "city", "amount") == {"Тбилиси": 350, "Батуми": 70, None: 30}


# --- 6. dedupe -------------------------------------------------------------

def test_dedupe():
    rows = [
        {"a": 1, "b": "x", "n": 1},
        {"a": 1, "b": "x", "n": 2},
        {"a": 2, "b": "x", "n": 3},
    ]
    out = z.dedupe(rows, ["a", "b"])
    assert len(out) == 2
    assert out[0]["n"] == 1, "оставлять надо первое вхождение"
    assert z.dedupe(rows, ["a", "b", "n"]) == rows


# --- 7. median -------------------------------------------------------------

def test_median():
    assert z.median([3, 1, 2]) == 2
    assert z.median([1, 2, 3, 4]) == 2.5
    assert z.median([5]) == 5
    assert z.median([]) is None
    assert z.median([1, None, 3]) == 2, "None игнорируется, а не считается нулём"


# --- 8. percentile ---------------------------------------------------------

def test_percentile():
    vals = [1, 2, 3, 4, 5]
    assert z.percentile(vals, 0.5) == 3
    assert z.percentile(vals, 0) == 1
    assert z.percentile(vals, 1) == 5
    assert z.percentile(vals, 0.9) == pytest.approx(4.6)
    assert z.percentile([], 0.5) is None


# --- 9. top_n --------------------------------------------------------------

def test_top_n():
    counts = {"a": 3, "b": 5, "c": 3, "d": 1}
    assert z.top_n(counts, 2) == [("b", 5), ("a", 3)]
    assert z.top_n(counts, 3) == [("b", 5), ("a", 3), ("c", 3)], \
        "при равных значениях сортировка по ключу"
    assert z.top_n(counts, 99) == [("b", 5), ("a", 3), ("c", 3), ("d", 1)]


# --- 10. conversion_funnel -------------------------------------------------

def test_conversion_funnel():
    steps = [("visit", 1000), ("signup", 250), ("deposit", 50)]
    out = z.conversion_funnel(steps)
    assert out[0] == ("visit", 1000, None)
    assert out[1] == ("signup", 250, 25.0)
    assert out[2] == ("deposit", 50, 20.0)


# --- 11. moving_average ----------------------------------------------------

def test_moving_average():
    assert z.moving_average([1, 2, 3, 4, 5], 3) == [1.0, 1.5, 2.0, 3.0, 4.0]
    assert z.moving_average([10], 3) == [10.0]


# --- 12. bucketize ---------------------------------------------------------

BOUNDS = [20, 50, 100]
LABELS = ["1. до 20", "2. 20-50", "3. 50-100", "4. 100+"]


@pytest.mark.parametrize("value, expected", [
    (5, "1. до 20"), (20, "2. 20-50"), (49.9, "2. 20-50"),
    (50, "3. 50-100"), (250, "4. 100+"), (None, None),
])
def test_bucketize(value, expected):
    assert z.bucketize(value, BOUNDS, LABELS) == expected


# --- 13. group_values ------------------------------------------------------

def test_group_values():
    out = z.group_values(RECORDS, "city", "amount")
    assert out["Тбилиси"] == [100, 250]
    assert out["Батуми"] == [70, None]
    assert None in out


# --- 14. fill_missing_dates ------------------------------------------------

def test_fill_missing_dates():
    counts = {date(2026, 3, 1): 5, date(2026, 3, 3): 2}
    out = z.fill_missing_dates(counts, date(2026, 3, 1), date(2026, 3, 4))
    assert out == {
        date(2026, 3, 1): 5,
        date(2026, 3, 2): 0,
        date(2026, 3, 3): 2,
        date(2026, 3, 4): 0,
    }


# --- 15. flatten -----------------------------------------------------------

def test_flatten():
    assert z.flatten([1, [2, 3], [[4], 5]]) == [1, 2, 3, 4, 5]
    assert z.flatten([]) == []
    assert z.flatten([[[[7]]]]) == [7]


# --- 16. parse_utm ---------------------------------------------------------

def test_parse_utm():
    url = "https://site.com/land?utm_source=google&utm_medium=cpc&utm_campaign=brand&gclid=abc"
    assert z.parse_utm(url) == {
        "utm_source": "google", "utm_medium": "cpc", "utm_campaign": "brand"
    }
    assert z.parse_utm("https://site.com/land") == {}
    assert z.parse_utm("https://site.com/?utm_source=fb#frag") == {"utm_source": "fb"}


# --- 17. retention_day_n ---------------------------------------------------

def test_retention_day_n():
    regs = {1: date(2026, 3, 1), 2: date(2026, 3, 1), 3: date(2026, 3, 2), 4: date(2026, 3, 2)}
    sessions = [
        (1, date(2026, 3, 2)),      # D1 для игрока 1
        (2, date(2026, 3, 5)),      # не D1
        (3, date(2026, 3, 3)),      # D1 для игрока 3
        (3, date(2026, 3, 9)),      # D7 для игрока 3
    ]
    assert z.retention_day_n(regs, sessions, 1) == 50.0
    assert z.retention_day_n(regs, sessions, 7) == 25.0
    assert z.retention_day_n({}, sessions, 1) is None


# --- 18. safe_div ----------------------------------------------------------

def test_safe_div():
    assert z.safe_div(10, 4) == 2.5
    assert z.safe_div(10, 0) is None
    assert z.safe_div(10, 0, 0) == 0
    assert z.safe_div(None, 5) is None
    assert z.safe_div(10, None, "н/д") == "н/д"


# --- 19. read_csv_rows -----------------------------------------------------

def test_read_csv_rows():
    rows = z.read_csv_rows(FIXTURE)
    assert len(rows) == 10
    assert isinstance(rows[0], dict)
    assert rows[0]["master"] == "Иван Петров"
    assert rows[0]["id_zapisi"] == "1", "csv возвращает строки, а не числа"


# --- 20. summarize ---------------------------------------------------------

def test_summarize():
    r = z.summarize(FIXTURE)
    assert r["rows"] == 10
    assert r["after_dedupe"] == 9, \
        "имя мастера надо привести к канону ДО поиска дубликатов"
    assert r["completed"] == 7
    assert r["revenue"] == pytest.approx(8660.0)
    assert r["avg_price"] == pytest.approx(1443.33, abs=0.01)
    assert r["median_price"] == pytest.approx(1400.0)
    assert r["masters"] == 6
