"""
Проверка решений тренажёра спринта 15.

Запуск:      make test SPRINT=15
Одна задача: python3 -m pytest sprint-15-komanda/trenazher -q -k smells
"""

import numpy as np
import pandas as pd
import pytest

import zadachi as z


DF = pd.DataFrame({
    "id": [1, 2, 2, 3, None],
    "status": ["ok", "ok", "bad", "ok", None],
    "amount": [10.0, 20.0, -5.0, 1e9, 30.0],
    "ts": ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05"],
})

CLEAN = pd.DataFrame({"id": [1, 2, 3], "status": ["ok", "ok", "pending"],
                      "amount": [10.0, 20.0, 30.0]})


# --- 1. уникальность -------------------------------------------------------

def test_test_unique():
    bad = z.test_unique(DF, "id")
    assert bad["test"] == "unique(id)"
    assert bad["passed"] is False
    assert bad["failed_rows"] == 2, \
        "две строки участвуют в дубле — считаем обе, а не одну лишнюю"
    assert bad["detail"] != ""
    ok = z.test_unique(CLEAN, "id")
    assert ok["passed"] is True and ok["failed_rows"] == 0 and ok["detail"] == ""


def test_test_unique_composite_key():
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "y", "x"]})
    assert z.test_unique(df, ["a", "b"])["passed"] is True
    assert z.test_unique(df, "a")["passed"] is False, \
        "по одному столбцу ключ не уникален, по паре — уникален"


# --- 2. пропуски -----------------------------------------------------------

def test_test_not_null():
    out = z.test_not_null(DF, ["id", "status"])
    assert out["test"] == "not_null(id,status)"
    assert out["passed"] is False
    assert out["failed_rows"] == 2, "по одному пропуску в каждом столбце"
    assert "id" in out["detail"] and "status" in out["detail"]
    assert z.test_not_null(CLEAN, ["id", "amount"])["passed"] is True


# --- 3. допустимые значения ------------------------------------------------

def test_test_accepted_values():
    out = z.test_accepted_values(DF, "status", ["ok", "pending"])
    assert out["passed"] is False
    assert out["failed_rows"] == 2, \
        "'bad' и NULL. NULL обязан считаться нарушением, иначе тест " \
        "молча пропустит пропуски"
    assert z.test_accepted_values(CLEAN, "status", ["ok", "pending"])["passed"] is True


# --- 4. диапазон -----------------------------------------------------------

def test_test_range():
    out = z.test_range(DF, "amount", 0, 1000)
    assert out["test"] == "range(amount, 0..1000)"
    assert out["failed_rows"] == 2, "−5 ниже нижней границы, миллиард выше верхней"
    assert z.test_range(DF, "amount", lo=-100)["passed"] is True, \
        "верхняя граница не задана — сверху не ограничиваем"
    assert z.test_range(CLEAN, "amount", 0, 100)["passed"] is True


def test_test_range_boundaries_included():
    df = pd.DataFrame({"x": [0.0, 100.0]})
    assert z.test_range(df, "x", 0, 100)["passed"] is True, "границы включаются"
    assert z.test_range(pd.DataFrame({"x": ["нет"]}), "x", 0, 1)["passed"] is False, \
        "нечисловое значение — нарушение, а не пропуск проверки"


# --- 5. ссылочная целостность ----------------------------------------------

def test_test_relationships():
    child = pd.DataFrame({"order_id": [1, 2, 3, 4], "cust": [10, 11, 99, None]})
    parent = pd.DataFrame({"cust": [10, 11, 12]})
    out = z.test_relationships(child, parent, "cust", "cust")
    assert out["passed"] is False
    assert out["failed_rows"] == 1, "99 — сирота, NULL не проверяется"
    assert "99" in out["detail"]


# --- 6. сходимость ---------------------------------------------------------

def test_test_recon():
    assert z.test_recon(7291061.09, 7291061.09)["passed"] is True
    bad = z.test_recon(7100000.0, 7291061.09)
    assert bad["passed"] is False
    assert "7291061" in bad["detail"] or "7291061.09" in bad["detail"]
    assert z.test_recon(7291000.0, 7291061.09)["passed"] is True, \
        "расхождение 61 из 7,29 млн — это 0,0008%, внутри допуска"
    assert z.test_recon(7291000.0, 7291061.09, tol=1e-9)["passed"] is False


# --- 7. свежесть -----------------------------------------------------------

def test_test_freshness():
    late = z.test_freshness(DF, "ts", "2026-06-06 12:00:00", 24)
    assert late["passed"] is False
    assert late["lag_hours"] == pytest.approx(36.0)
    assert late["severity"] == "warn", \
        "устаревшие данные будят дежурного, а не удаляют витрину"
    ok = z.test_freshness(DF, "ts", "2026-06-06 12:00:00", 48)
    assert ok["passed"] is True and ok["lag_hours"] == pytest.approx(36.0)
    assert z.test_freshness(pd.DataFrame({"ts": [None]}), "ts",
                            "2026-06-06", 24)["passed"] is False


# --- 8. свод набора --------------------------------------------------------

def test_run_suite_warning_does_not_block():
    results = [
        z.test_unique(CLEAN, "id"),
        z.test_recon(100.0, 100.0),
        z.test_freshness(DF, "ts", "2026-06-06 12:00:00", 24),
    ]
    out = z.run_suite(results)
    assert out["total"] == 3 and out["failed"] == 1
    assert out["errors"] == 0 and out["warnings"] == 1
    assert out["can_publish"] is True, \
        "предупреждение о свежести не должно блокировать публикацию"


def test_run_suite_error_blocks():
    results = [z.test_unique(DF, "id"), z.test_recon(100.0, 100.0)]
    out = z.run_suite(results)
    assert out["errors"] == 1 and out["can_publish"] is False
    assert out["failed_tests"] == ["unique(id)"]


# --- 9. параметры ----------------------------------------------------------

def test_resolve_params():
    p = z.resolve_params({"period": "month", "tol": 0.01, "city": None},
                         {"tol": 0.02}, required=["period"])
    assert p == {"period": "month", "tol": 0.02, "city": None}


def test_resolve_params_typo_is_an_error():
    with pytest.raises(KeyError):
        z.resolve_params({"date_from": "2026-01-01"}, {"date_form": "2026-02-01"})


def test_resolve_params_required():
    with pytest.raises(ValueError):
        z.resolve_params({"city": None}, required=["city"])


# --- 10. воспроизводимая выборка -------------------------------------------

BIG = pd.DataFrame({"g": ["a"] * 60 + ["b"] * 40, "v": range(100)})


def test_deterministic_sample_is_deterministic():
    a = z.deterministic_sample(BIG, 10, 42)
    b = z.deterministic_sample(BIG, 10, 42)
    assert len(a) == 10
    assert a.equals(b), "один seed — одна и та же выборка"
    assert not a.equals(z.deterministic_sample(BIG, 10, 7))
    assert list(a.index) == sorted(a.index), "результат отсортирован по индексу"


def test_deterministic_sample_edges():
    assert len(z.deterministic_sample(BIG, 500, 1)) == 100
    with pytest.raises(ValueError):
        z.deterministic_sample(BIG, 0, 1)


def test_deterministic_sample_stratified():
    s = z.deterministic_sample(BIG, 10, 42, stratify_col="g")
    assert len(s) == 10, "итог ровно n, остаток достаётся последней группе"
    assert s["g"].value_counts().to_dict() == {"a": 6, "b": 4}, \
        "доли групп сохраняются: 60/40"


# --- 11. порядок ячеек ноутбука --------------------------------------------

def test_notebook_run_order_broken():
    nb = {"cells": [{"cell_type": "code", "execution_count": 1},
                    {"cell_type": "markdown"},
                    {"cell_type": "code", "execution_count": 5},
                    {"cell_type": "code", "execution_count": 3},
                    {"cell_type": "code", "execution_count": None}]}
    out = z.notebook_run_order(nb)
    assert out["code_cells"] == 4 and out["executed"] == 3
    assert out["order"] == [1, 5, 3]
    assert out["not_executed"] == [3], "позиция среди кодовых ячеек, с нуля"
    assert out["in_order"] is False
    assert out["reproducible"] is False, \
        "ячейка 5 выполнена раньше ячейки 3 — результат нельзя повторить"


def test_notebook_run_order_ok():
    nb = {"cells": [{"cell_type": "code", "execution_count": 1},
                    {"cell_type": "markdown"},
                    {"cell_type": "code", "execution_count": 2}]}
    out = z.notebook_run_order(nb)
    assert out["in_order"] is True and out["reproducible"] is True
    assert out["not_executed"] == []


# --- 12. запахи SQL --------------------------------------------------------

BAD_SQL = """-- витрина по ресторанам
SELECT *
FROM orders o
JOIN restaurants r ON r.restaurant_id = o.restaurant_id
WHERE o.created_at BETWEEN '2025-10-01' AND '2026-06-29'
  AND o.promo_code <> 'NONE'
"""

GOOD_SQL = """SELECT o.order_id, o.items_total
FROM orders o
INNER JOIN restaurants r ON r.restaurant_id = o.restaurant_id
WHERE o.created_at >= :date_from
  AND o.created_at < :date_to
  AND (o.promo_code IS NULL OR o.promo_code <> :excluded)
"""


def test_sql_smells_finds_all():
    found = z.sql_smells(BAD_SQL)
    rules = [f["rule"] for f in found]
    assert set(rules) == {"select_star", "bare_join", "hardcoded_date",
                          "between_timestamp", "not_equal_null"}
    by = {f["rule"]: f for f in found}
    assert by["select_star"]["line"] == 2
    assert by["bare_join"]["line"] == 4
    assert by["hardcoded_date"]["line"] == 5
    assert by["not_equal_null"]["line"] == 6
    assert by["select_star"]["text"] == "SELECT *", "исходная строка, обрезанная"


def test_sql_smells_rule_order():
    rules = [f["rule"] for f in z.sql_smells(BAD_SQL)]
    order = [r[0] for r in z.SQL_SMELLS]
    assert rules == sorted(rules, key=order.index), \
        "обход по правилам снаружи, по строкам внутри"


def test_sql_smells_clean_query():
    assert z.sql_smells(GOOD_SQL) == []


def test_sql_smells_implicit_join():
    found = z.sql_smells("SELECT a.x FROM t1 a, t2 b WHERE a.id = b.id")
    assert [f["rule"] for f in found] == ["implicit_join"]
    assert z.sql_smells("SELECT x FROM t1, t2")[0]["rule"] == "implicit_join"


def test_sql_smells_ignores_comments():
    assert z.sql_smells("-- раньше тут был SELECT *\nSELECT o.id FROM orders o") == []


# --- 13. размер PR ---------------------------------------------------------

DIFF = """--- a/mart.sql
+++ b/mart.sql
@@
-SELECT *
+SELECT o.id
+FROM orders o
--- a/README.md
+++ b/README.md
@@
+docs
"""


def test_diff_stats():
    out = z.diff_stats(DIFF)
    assert out["files"] == ["mart.sql", "README.md"]
    assert out["n_files"] == 2
    assert out["added"] == 3 and out["removed"] == 1, \
        "строки заголовков диффа в подсчёт не входят"
    assert out["total_changed"] == 4
    assert out["too_big"] is False
    assert out["verdict"] == "размер приемлемый"


def test_diff_stats_too_big():
    out = z.diff_stats(DIFF, big_pr_lines=2)
    assert out["too_big"] is True
    assert out["verdict"] == "разбить на несколько PR"


# --- 14. тяжесть -----------------------------------------------------------

def test_classify_severity():
    assert z.classify_severity(True) == "blocker"
    assert z.classify_severity(False, breaks_pipeline=True) == "blocker"
    assert z.classify_severity(False, is_risky=True) == "major"
    assert z.classify_severity(False, is_style=True) == "nit"
    assert z.classify_severity(False) == "minor"
    assert z.classify_severity(True, is_style=True) == "blocker", \
        "меняет результат — значит blocker, даже если заодно некрасиво"


# --- 15. замечание ---------------------------------------------------------

def test_review_finding():
    f = z.review_finding("mart.sql:12", "джойн задваивает выручку",
                         "агрегируй позиции до соединения", "blocker")
    assert f["blocking"] is True
    assert f["location"] == "mart.sql:12"
    assert z.review_finding(" a ", " b ", " c ", "nit")["location"] == "a"
    assert z.review_finding("a", "b", "c", "major")["blocking"] is False


def test_review_finding_requires_suggestion():
    with pytest.raises(ValueError):
        z.review_finding("mart.sql:12", "тут неправильно", "   ", "blocker")
    with pytest.raises(ValueError):
        z.review_finding("mart.sql:12", "проблема", "предложение", "critical")


# --- 16. свод ревью --------------------------------------------------------

F_BLOCK = {"location": "a", "problem": "p", "suggestion": "s",
           "severity": "blocker", "blocking": True}
F_MAJOR = {"location": "b", "problem": "p", "suggestion": "s",
           "severity": "major", "blocking": False}
F_NIT = {"location": "c", "problem": "p", "suggestion": "s",
         "severity": "nit", "blocking": False}


def test_review_summary_verdicts():
    assert z.review_summary([F_BLOCK, F_MAJOR, F_NIT])["verdict"] == "вернуть на доработку"
    assert z.review_summary([F_MAJOR, F_NIT])["verdict"] == "принять с правками"
    assert z.review_summary([F_NIT])["verdict"] == "принять"
    assert z.review_summary([])["verdict"] == "принять"


def test_review_summary_splits_mandatory():
    out = z.review_summary([F_BLOCK, F_MAJOR, F_NIT])
    assert out["by_severity"] == {"blocker": 1, "major": 1, "minor": 0, "nit": 1}
    assert len(out["mandatory"]) == 2 and len(out["optional"]) == 1
    assert out["can_merge"] is False


# --- 17. полнота постановки ------------------------------------------------

def test_requirements_gaps():
    out = z.requirements_gaps({"question": "какая конверсия?", "period": "  ",
                               "metric_definition": None, "segments": "город",
                               "decision": "решаем про бюджет", "deadline": "пятница"})
    assert out["missing"] == ["metric_definition", "period"], \
        "порядок как в списке требуемых полей, пробелы — это отсутствие"
    assert out["ready"] is False
    assert "за какой период" in out["questions"]


def test_requirements_gaps_decision_is_required():
    task = {f: "есть" for f in z.REQUIRED_TASK_FIELDS}
    assert z.requirements_gaps(task)["ready"] is True
    task["decision"] = None
    out = z.requirements_gaps(task)
    assert out["missing"] == ["decision"], \
        ("вопрос про решение чаще всего и отменяет задачу: выясняется, "
         "что решение уже принято")


# --- 18. полнота спецификации метрики --------------------------------------

def test_metric_spec_complete():
    out = z.metric_spec_complete({"name": "CR в первый заказ", "definition": "доля",
                                  "numerator": "заказавшие", "denominator": "все",
                                  "unit": "клиент", "period": "месяц"})
    assert out["missing"] == ["owner", "sql_ref"]
    assert out["filled"] == 6 and out["required"] == 8
    assert out["completeness"] == pytest.approx(0.75)
    assert out["complete"] is False
    full = {f: "x" for f in z.REQUIRED_SPEC_FIELDS}
    assert z.metric_spec_complete(full)["complete"] is True
