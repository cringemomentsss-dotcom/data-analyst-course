"""
Проверка решений тренажёра спринта 16.

Запуск:      make test SPRINT=16
Одна задача: python3 -m pytest sprint-16-optimizaciya/trenazher -q -k scd2

Планы в тестах — настоящие, снятые на схеме `dwh` из проекта этого спринта.
"""

import numpy as np
import pandas as pd
import pytest

import zadachi as z


PLAN_SEQ = """ Aggregate  (cost=205012.00..205012.01 rows=1 width=40) (actual time=18183.914..18184.960 rows=1 loops=1)
   ->  Seq Scan on events  (cost=0.00..204812.00 rows=40000 width=6) (actual time=14965.938..18101.013 rows=459218 loops=1)
         Filter: (date_trunc('month'::text, event_ts) = '2026-03-01 00:00:00'::timestamp without time zone)
         Rows Removed by Filter: 7540782
 Planning Time: 15.929 ms
 Execution Time: 19718.648 ms"""

PLAN_SUBPLAN = """ Limit  (cost=0.00..1588253.53 rows=20 width=22) (actual time=13677.289..19272.281 rows=20 loops=1)
   ->  Seq Scan on orders o  (cost=0.00..4253263552.18 rows=53559 width=22) (actual time=12071.692..17666.617 rows=20 loops=1)
         Filter: ((created_at >= '2026-06-01 00:00:00'::timestamp) AND (status = 'paid'::text))
         Rows Removed by Filter: 551
         SubPlan 1
           ->  Aggregate  (cost=79412.01..79412.02 rows=1 width=8) (actual time=883.002..883.003 rows=1 loops=20)
                 ->  Seq Scan on order_lines l  (cost=0.00..79412.00 rows=4 width=0) (actual time=367.250..881.625 rows=3 loops=20)
                       Filter: (order_id = o.order_id)
                       Rows Removed by Filter: 3999997
 Execution Time: 19794.028 ms"""

PLAN_NO_ANALYZE = """ Aggregate  (cost=205012.00..205012.01 rows=1 width=40)
   ->  Seq Scan on events  (cost=0.00..204812.00 rows=40000 width=6)
         Filter: (date_trunc('month'::text, event_ts) = '2026-03-01'::timestamp)"""


# --- 1. разбор плана -------------------------------------------------------

def test_parse_plan_flat():
    n = z.parse_plan(PLAN_SEQ)
    assert len(n) == 2, "два узла; Filter, Planning Time и Execution Time — не узлы"
    assert n[0]["node"] == "Aggregate" and n[0]["depth"] == 0
    assert n[1]["node"] == "Seq Scan" and n[1]["depth"] == 1
    assert n[1]["table"] == "events"
    assert n[1]["est_rows"] == 40000
    assert n[1]["act_rows"] == pytest.approx(459218.0)
    assert n[1]["removed_rows"] == pytest.approx(7540782.0)
    assert n[1]["rows_scanned"] == pytest.approx(8000000.0), \
        "459 218 вернул, 7 540 782 отбросил — просмотрел всю таблицу"


def test_parse_plan_multiplies_by_loops():
    n = z.parse_plan(PLAN_SUBPLAN)
    assert [x["node"] for x in n] == ["Limit", "Seq Scan", "Aggregate", "Seq Scan"]
    assert [x["depth"] for x in n] == [0, 1, 2, 3], \
        "SubPlan добавляет уровень, хотя сам узлом не является"
    inner = n[3]
    assert inner["loops"] == 20
    assert inner["total_ms"] == pytest.approx(881.625 * 20, rel=1e-6), \
        "883 мс на проход — это 17,6 секунды на двадцати проходах"
    assert inner["act_rows"] == pytest.approx(60.0)
    assert inner["rows_scanned"] == pytest.approx(80_000_000.0)


def test_parse_plan_without_analyze():
    n = z.parse_plan(PLAN_NO_ANALYZE)
    assert len(n) == 2
    assert n[1]["act_rows"] is None and n[1]["total_ms"] is None
    assert n[1]["est_rows"] == 40000 and n[1]["cost"] == pytest.approx(204812.00)


# --- 2. узкое место --------------------------------------------------------

def test_plan_bottleneck_self_time():
    b = z.plan_bottleneck(z.parse_plan(PLAN_SUBPLAN))
    assert b["node"] == "Seq Scan" and b["table"] == "order_lines"
    assert b["self_ms"] == pytest.approx(17632.5, abs=1.0)
    assert b["share"] > 0.85, \
        "90% времени запроса — во внутреннем скане, а не в корне"


def test_plan_bottleneck_edges():
    assert z.plan_bottleneck([]) is None
    assert z.plan_bottleneck(z.parse_plan(PLAN_NO_ANALYZE)) is None, \
        "без ANALYZE времени нет, и узкое место по плану не определить"
    b = z.plan_bottleneck(z.parse_plan(PLAN_SEQ))
    assert b["table"] == "events"


# --- 3. ошибки оценки ------------------------------------------------------

def test_estimate_error():
    e = z.estimate_error(z.parse_plan(PLAN_SEQ))
    assert len(e) == 1
    assert e[0]["table"] == "events"
    assert e[0]["ratio"] == pytest.approx(11.48, abs=0.01)
    assert e[0]["direction"] == "недооценил"


def test_estimate_error_sorted_and_threshold():
    e = z.estimate_error(z.parse_plan(PLAN_SUBPLAN))
    assert [r["ratio"] for r in e] == sorted([r["ratio"] for r in e], reverse=True)
    assert e[0]["table"] == "orders" and e[0]["direction"] == "переоценил"
    assert e[0]["ratio"] == pytest.approx(2677.95, abs=0.1)
    assert z.estimate_error(z.parse_plan(PLAN_SUBPLAN), threshold=5000.0) == []


# --- 4. сканы --------------------------------------------------------------

def test_find_seq_scans():
    s = z.find_seq_scans(z.parse_plan(PLAN_SEQ))
    assert len(s) == 1
    assert s[0]["table"] == "events"
    assert s[0]["rows"] == pytest.approx(8_000_000.0)
    assert s[0]["returned"] == pytest.approx(459218.0)


def test_find_seq_scans_counts_scanned_not_returned():
    s = z.find_seq_scans(z.parse_plan(PLAN_SUBPLAN))
    assert len(s) == 1 and s[0]["table"] == "order_lines"
    assert s[0]["rows"] == pytest.approx(80_000_000.0)
    assert s[0]["returned"] == pytest.approx(60.0), \
        ("вернул 60 строк, просмотрел 80 миллионов. Первое число видно "
         "сразу, второе надо сложить с Rows Removed by Filter")
    assert z.find_seq_scans(z.parse_plan(PLAN_SUBPLAN), min_rows=10**9) == []


# --- 5. диагноз ------------------------------------------------------------

def test_explain_verdict_subplan():
    v = z.explain_verdict(z.parse_plan(PLAN_SUBPLAN))
    problems = {f["problem"] for f in v["findings"]}
    assert "узел выполняется многократно" in problems
    assert "последовательный скан большой таблицы ради малой доли строк" in problems
    assert "планировщик ошибся в оценке числа строк" in problems
    assert v["clean"] is False
    for f in v["findings"]:
        assert set(f) == {"node", "table", "problem", "evidence", "fix"}
        assert any(ch.isdigit() for ch in f["evidence"]), \
            "в основании должны быть числа, а не слова"


def test_explain_verdict_deduplicates():
    v = z.explain_verdict(z.parse_plan(PLAN_SUBPLAN))
    keys = [(f["node"], f["table"], f["problem"]) for f in v["findings"]]
    assert len(keys) == len(set(keys))
    assert v["n"] == len(v["findings"])


def test_explain_verdict_clean_plan():
    fast = """ Index Only Scan using ix_ord_user on orders  (cost=0.43..8.45 rows=1 width=4) (actual time=0.021..0.022 rows=1 loops=1)"""
    assert z.explain_verdict(z.parse_plan(fast))["clean"] is True


# --- 6. применимость индекса -----------------------------------------------

@pytest.mark.parametrize("predicate,usable", [
    ("created_at >= '2026-06-01'", True),
    ("status IN ('paid','refunded')", True),
    ("total_amount BETWEEN 10 AND 20", True),
    ("title LIKE 'Товар 9%'", True),
    ("date_trunc('month', event_ts) = '2026-03-01'", False),
    ("lower(email) = 'a@b.c'", False),
    ("user_id::text = '12345'", False),
    ("title LIKE '%999%'", False),
])
def test_index_usable(predicate, usable):
    assert z.index_usable(predicate)["usable"] is usable


def test_index_usable_names_the_column_and_reason():
    f = z.index_usable("date_trunc('month', event_ts) = '2026-03-01'")
    assert f["column"] == "event_ts", "столбец внутри функции, а не литерал"
    assert "функци" in f["reason"].lower()
    c = z.index_usable("user_id::text = '12345'")
    assert c["column"] == "user_id" and "тип" in c["reason"].lower()
    l = z.index_usable("title LIKE '%999%'")
    assert "триграмм" in l["reason"].lower()


# --- 7. составной индекс ---------------------------------------------------

def test_composite_order():
    out = z.composite_order(["country", "device"], ["event_ts"], ["revenue"])
    assert out["columns"] == ["country", "device", "event_ts", "revenue"]
    assert out["definition"] == "(country, device, event_ts, revenue)"
    assert out["warning"] != "", \
        "после диапазонного столбца индекс не даёт готовый порядок"


def test_composite_order_no_duplicates_no_warning():
    out = z.composite_order(["a"], [], ["a", "b"])
    assert out["columns"] == ["a", "b"], "повторов быть не должно"
    assert out["warning"] == "", "диапазона нет — предупреждать не о чем"


# --- 8. цена индекса -------------------------------------------------------

def test_index_write_cost():
    out = z.index_write_cost(8_000_000, 50_000, n_indexes_before=2)
    assert out["size_mb"] == pytest.approx(183.105, abs=0.01)
    assert out["write_overhead_pct"] == pytest.approx(50.0), \
        "было два индекса, стал третий — работы на запись на половину больше"
    assert out["indexes_after"] == 3
    assert z.index_write_cost(1000, 10, n_indexes_before=4)["write_overhead_pct"] \
        == pytest.approx(25.0)


# --- 9. зернистость --------------------------------------------------------

DF_GRAIN = pd.DataFrame({"d": ["2026-01-01"] * 3, "dev": ["ios", "ios", "web"],
                         "n": [1, 2, 3]})


def test_grain_check():
    bad = z.grain_check(DF_GRAIN, ["d", "dev"])
    assert bad["ok"] is False
    assert bad["rows"] == 3 and bad["unique_keys"] == 2
    assert bad["violating_rows"] == 2, "обе строки дубля, а не одна лишняя"
    assert z.grain_check(DF_GRAIN, ["d", "dev", "n"])["ok"] is True


# --- 10. звезда ------------------------------------------------------------

def test_star_schema_check():
    fact = pd.DataFrame({"user_id": [1, 2, 99], "product_id": [10, 11, 10],
                         "amt": [1.0, 2.0, 3.0]})
    dims = {"user_id": pd.DataFrame({"user_id": [1, 2, 3]}),
            "product_id": pd.DataFrame({"product_id": [10, 11]})}
    out = z.star_schema_check(fact, dims)
    assert out["keys"] == ["user_id", "product_id"], "ключи ищутся по суффиксу _id"
    assert out["ok"] is False and len(out["problems"]) == 1
    assert {c["key"]: c["orphans"] for c in out["checked"]} == {"user_id": 1,
                                                               "product_id": 0}


def test_star_schema_missing_dimension():
    fact = pd.DataFrame({"seller_id": [1], "amt": [1.0]})
    out = z.star_schema_check(fact, {})
    assert out["ok"] is False
    assert "seller_id" in out["problems"][0]


# --- 11-12. SCD2 -----------------------------------------------------------

DIM = pd.DataFrame({"user_id": [1], "plan": ["free"],
                    "valid_from": ["2026-01-01"], "valid_to": [None],
                    "is_current": [True]})


def test_scd2_apply_opens_new_version():
    r = z.scd2_apply(DIM, 1, "user_id", {"plan": "pro"}, "2026-03-15")
    assert r["changed"] is True
    t = r["table"]
    assert len(t) == 2
    old = t[~t["is_current"].astype(bool)].iloc[0]
    new = t[t["is_current"].astype(bool)].iloc[0]
    assert old["plan"] == "free"
    assert pd.Timestamp(old["valid_to"]) == pd.Timestamp("2026-03-15")
    assert new["plan"] == "pro" and pd.isna(new["valid_to"])


def test_scd2_apply_is_a_noop_when_nothing_changed():
    r1 = z.scd2_apply(DIM, 1, "user_id", {"plan": "pro"}, "2026-03-15")
    r2 = z.scd2_apply(r1["table"], 1, "user_id", {"plan": "pro"}, "2026-04-01")
    assert r2["changed"] is False
    assert len(r2["table"]) == 2, \
        ("иначе ежедневная загрузка создаёт новую версию каждый день "
         "и за год делает 365 копий одного клиента")


def test_scd2_lookup():
    t = z.scd2_apply(DIM, 1, "user_id", {"plan": "pro"}, "2026-03-15")["table"]
    assert z.scd2_lookup(t, 1, "user_id", "2026-02-01", "plan") == "free"
    assert z.scd2_lookup(t, 1, "user_id", "2026-06-01", "plan") == "pro"
    assert z.scd2_lookup(t, 1, "user_id", "2026-03-15", "plan") == "pro", \
        "интервал закрыт слева и открыт справа: в день смены действует новая"
    assert z.scd2_lookup(t, 1, "user_id", "2025-01-01", "plan") is None
    assert z.scd2_lookup(t, 42, "user_id", "2026-06-01", "plan") is None


# --- 13. окно инкремента ---------------------------------------------------

def test_incremental_window():
    w = z.incremental_window("2026-06-01 10:00", "2026-06-01 14:00")
    assert w["start"] == pd.Timestamp("2026-06-01 07:00")
    assert w["end"] == pd.Timestamp("2026-06-01 14:00")
    assert w["hours"] == pytest.approx(7.0)
    assert w["capped"] is False and w["overlap_hours"] == pytest.approx(3.0)


def test_incremental_window_capped():
    w = z.incremental_window("2026-01-01", "2026-06-01")
    assert w["capped"] is True
    assert w["start"] == pd.Timestamp("2026-05-25")
    assert w["hours"] == pytest.approx(168.0)
    assert w["overlap_hours"] == pytest.approx(0.0)


# --- 14-15. upsert и идемпотентность ---------------------------------------

TARGET = pd.DataFrame({"k": [1, 2], "v": [10, 20]})
BATCH = pd.DataFrame({"k": [2, 3, 3], "v": [99, 30, 31]})


def test_merge_upsert():
    m = z.merge_upsert(TARGET, BATCH, ["k"])
    assert m["updated"] == 1 and m["inserted"] == 1
    assert m["rows_after"] == 3
    t = m["table"]
    assert list(t["k"]) == [1, 2, 3], "результат отсортирован по ключу"
    assert list(t["v"]) == [10, 99, 31], \
        "из дублей батча по ключу 3 берётся последний"


def test_merge_upsert_into_empty():
    empty = pd.DataFrame({"k": pd.Series(dtype="int64"),
                          "v": pd.Series(dtype="int64")})
    m = z.merge_upsert(empty, BATCH, ["k"])
    assert m["updated"] == 0 and m["inserted"] == 2


def test_is_idempotent():
    out = z.is_idempotent(z.merge_upsert, TARGET, BATCH, ["k"])
    assert out["idempotent"] is True
    assert out["rows_first"] == 3 and out["rows_after_repeats"] == 3


def test_is_idempotent_catches_append():
    def naive_append(target, batch, key_cols):
        return {"table": pd.concat([target, batch], ignore_index=True)}
    out = z.is_idempotent(naive_append, TARGET, BATCH, ["k"])
    assert out["idempotent"] is False, \
        "INSERT без ключа задваивает при каждом перезапуске"
    assert out["rows_after_repeats"] > out["rows_first"]


# --- 16. поздние данные ----------------------------------------------------

def test_late_arriving():
    batch = pd.DataFrame({"event_ts": ["2026-06-01", "2026-05-28",
                                       "2026-06-01", "2026-06-02"]})
    out = z.late_arriving(batch)
    assert out["partitions"] == ["2026-05-28", "2026-06-01", "2026-06-02"]
    assert out["n_partitions"] == 3
    assert out["oldest"] == pd.Timestamp("2026-05-28")
    assert out["span_days"] == 5, \
        "в сегодняшнем батче событие пятидневной давности — старую партицию тоже пересчитывать"


def test_late_arriving_empty():
    out = z.late_arriving(pd.DataFrame({"event_ts": []}))
    assert out["partitions"] == [] and out["oldest"] is None
    assert out["span_days"] == 0


# --- 17. перезаливка -------------------------------------------------------

def test_backfill_plan():
    out = z.backfill_plan("2026-01-01", "2026-01-20", batch_days=7)
    assert out["n_batches"] == 3 and out["total_days"] == 20
    assert [b["days"] for b in out["batches"]] == [7, 7, 6]
    assert out["batches"][0]["from"] == pd.Timestamp("2026-01-01")
    assert out["batches"][-1]["to"] == pd.Timestamp("2026-01-20")


def test_backfill_plan_validates():
    assert z.backfill_plan("2026-01-01", "2026-01-01")["n_batches"] == 1
    with pytest.raises(ValueError):
        z.backfill_plan("2026-02-01", "2026-01-01")


# --- 18. порядок пересчёта -------------------------------------------------

DEPS = {"stg_events": [], "stg_orders": [],
        "core_sessions": ["stg_events"],
        "mart_daily": ["core_sessions", "stg_orders"]}


def test_pipeline_order():
    out = z.pipeline_order(DEPS)
    assert out["order"] == ["stg_events", "stg_orders", "core_sessions",
                            "mart_daily"]
    assert out["levels"] == {0: ["stg_events", "stg_orders"],
                             1: ["core_sessions"], 2: ["mart_daily"]}
    assert out["max_parallel"] == 2, \
        "два слоя staging считаются одновременно — столько воркеров и нужно"


def test_pipeline_order_includes_implicit_nodes():
    out = z.pipeline_order({"mart": ["stg"]})
    assert out["order"] == ["stg", "mart"], \
        "stg встречается только в значениях, но это тоже модель"


def test_pipeline_order_detects_cycle():
    with pytest.raises(ValueError):
        z.pipeline_order({"a": ["b"], "b": ["a"]})
