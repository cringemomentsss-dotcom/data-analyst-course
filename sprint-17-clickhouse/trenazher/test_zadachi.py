"""
Проверка решений тренажёра спринта 17.

Запуск:      make test SPRINT=17
Одна задача: python3 -m pytest sprint-17-clickhouse/trenazher -q -k funnel
"""

import numpy as np
import pandas as pd
import pytest

import zadachi as z


# --- 1. ORDER BY -----------------------------------------------------------

QUERIES = [{"filters": ["event_name", "event_ts"], "group_by": ["device"]},
           {"filters": ["event_name"], "group_by": ["country", "device"]},
           {"filters": ["user_id"], "group_by": []}]
COLS = {"event_name": 8, "event_ts": 8_000_000, "device": 3,
        "country": 6, "user_id": 200_000}


def test_choose_order_by():
    out = z.choose_order_by(QUERIES, COLS)
    assert out["order_by"][0] == "event_name", \
        "фильтруют в двух запросах из трёх, и уникальных всего восемь"
    assert out["order_by"] == ["event_name", "device", "user_id", "event_ts"], \
        "при равном весе вперёд идёт столбец с меньшей кардинальностью"
    assert out["definition"] == "ORDER BY (event_name, device, user_id, event_ts)"
    assert out["weights"]["event_name"] == 4


def test_choose_order_by_limits_and_empty():
    assert len(z.choose_order_by(QUERIES, COLS, max_cols=2)["order_by"]) == 2
    out = z.choose_order_by([], COLS)
    assert out["order_by"] == []
    assert out["definition"] == "ORDER BY tuple()"


def test_choose_order_by_ignores_unknown_columns():
    out = z.choose_order_by([{"filters": ["нет_такого"], "group_by": []}], COLS)
    assert out["order_by"] == []


# --- 2. партиционирование --------------------------------------------------

def test_partition_expr_month():
    out = z.partition_expr("event_ts", 15_000, 540)
    assert out["func"] == "toYYYYMM"
    assert out["parts"] == 18 and out["within_target"] is True
    assert out["expression"] == "PARTITION BY toYYYYMM(event_ts)"


def test_partition_expr_switches_to_week():
    out = z.partition_expr("event_ts", 500_000_000, 90)
    assert out["func"] == "toMonday", \
        "три месяца по месяцу — три партиции, это меньше десяти"
    assert out["parts"] == 13


def test_partition_expr_no_option_fits():
    out = z.partition_expr("event_ts", 100, 5)
    assert out["within_target"] is False
    assert out["func"] == "toYYYYMM"


# --- 3. типы ---------------------------------------------------------------

def test_pick_type_low_cardinality():
    out = z.pick_type("device", ["ios", "android", "web"] * 100)
    assert out["type"] == "LowCardinality(String)"


def test_pick_type_high_cardinality_string():
    out = z.pick_type("title", [f"Товар {i}" for i in range(20000)])
    assert out["type"] == "String", "20 тысяч уникальных — словарь не поможет"


def test_pick_type_integers_by_width():
    assert z.pick_type("qty", [1, 2, 3])["type"] == "UInt8"
    assert z.pick_type("user_id", [1, 2, 200_000])["type"] == "UInt32"
    assert z.pick_type("event_id", [1, 8_000_000_000])["type"] == "UInt64"
    assert z.pick_type("delta", [-5, 10])["type"].startswith("Int")


def test_pick_type_money_and_dates():
    assert z.pick_type("price", [1.5, 2.25, 4.0])["type"] == "Decimal(10, 2)"
    assert z.pick_type("ts", pd.to_datetime(["2026-01-01", "2026-02-01"]))["type"] \
        == "DateTime"


def test_pick_type_nullable_is_avoided_by_default():
    plain = z.pick_type("revenue", [1.5, 2.25, None, 4.0])
    assert plain["type"] == "Decimal(10, 2)", "Nullable дорог, по умолчанию не берём"
    assert "пропуск" in plain["reason"]
    allowed = z.pick_type("revenue", [1.5, 2.25, None, 4.0], nullable_ok=True)
    assert allowed["type"] == "Nullable(Decimal(10, 2))"


# --- 4. движки -------------------------------------------------------------

def test_engine_for():
    assert z.engine_for("append")["engine"] == "MergeTree"
    assert z.engine_for("dedup")["engine"] == "ReplacingMergeTree"
    assert z.engine_for("sum")["engine"] == "SummingMergeTree"
    assert z.engine_for("aggregate")["engine"] == "AggregatingMergeTree"
    with pytest.raises(ValueError):
        z.engine_for("upsert")


def test_engine_warning_about_background_merge():
    assert z.engine_for("append")["warning"] == ""
    w = z.engine_for("dedup")["warning"]
    assert w != "" and ("FINAL" in w or "GROUP BY" in w), \
        ("схлопывание идёт в фоне: прочитал сразу после вставки — увидел "
         "дубли. В Postgres UNIQUE это гарантия, здесь — обещание")


# --- 5. DDL ----------------------------------------------------------------

def test_ddl_for():
    ddl = z.ddl_for("course.events",
                    {"user_id": "UInt32", "event_ts": "DateTime",
                     "device": "LowCardinality(String)"},
                    "MergeTree", ["user_id", "event_ts"], "toYYYYMM(event_ts)")
    assert ddl.startswith("CREATE TABLE course.events")
    assert "ENGINE = MergeTree" in ddl
    assert "PARTITION BY toYYYYMM(event_ts)" in ddl
    assert "ORDER BY (user_id, event_ts)" in ddl
    assert "TTL" not in ddl
    lines = [l for l in ddl.splitlines() if l.startswith("    ")]
    assert len(lines) == 3
    assert lines[0].startswith("    user_id ") and lines[0].rstrip().endswith("UInt32,")


def test_ddl_for_empty_order_by_and_ttl():
    ddl = z.ddl_for("t", {"a": "UInt8"}, "MergeTree", [],
                    ttl="ts + INTERVAL 30 DAY DELETE")
    assert "ORDER BY tuple()" in ddl
    assert "TTL ts + INTERVAL 30 DAY DELETE" in ddl


# --- 6-9. массивы ----------------------------------------------------------

def test_array_join():
    df = pd.DataFrame({"u": [1, 2, 3], "names": [["a", "b"], ["c"], None]})
    out = z.array_join(df, "names")
    assert list(out["names"]) == ["a", "b", "c"]
    assert list(out["u"]) == [1, 1, 2]
    assert list(out.index) == [0, 1, 2]


def test_array_filter_map():
    assert z.array_filter_map([1, 2, 3, 4, 5], lambda x: x % 2 == 0,
                              lambda x: x * 10) == [20, 40]
    assert z.array_filter_map([], lambda x: True, lambda x: x) == []


EV = pd.DataFrame({
    "user_id": [1, 1, 1, 2],
    "event_name": ["view", "cart", "buy", "view"],
    "ts": ["2026-01-01 10:00", "2026-01-01 10:05", "2026-01-01 11:00",
           "2026-01-02 09:00"]})


def test_events_to_array():
    out = z.events_to_array(EV)
    assert len(out) == 2, "по строке на пользователя"
    assert list(out["user_id"]) == [1, 2]
    assert out.iloc[0]["names"] == ["view", "cart", "buy"], \
        "массив отсортирован по времени"
    assert out.iloc[0]["n"] == 3 and out.iloc[1]["n"] == 1
    assert len(out.iloc[0]["times"]) == 3


def test_events_to_array_sorts_unordered_input():
    shuffled = EV.iloc[[2, 0, 3, 1]].reset_index(drop=True)
    out = z.events_to_array(shuffled)
    assert out.iloc[0]["names"] == ["view", "cart", "buy"]


def test_has_sequence():
    assert z.has_sequence(["view", "x", "cart", "y", "buy"],
                          ["view", "cart", "buy"]) is True, \
        "между шагами могут быть посторонние события"
    assert z.has_sequence(["cart", "view", "buy"],
                          ["view", "cart", "buy"]) is False, \
        "порядок обязателен"
    assert z.has_sequence(["view"], []) is True
    assert z.has_sequence([], ["view"]) is False


# --- 10-11. комбинаторы ----------------------------------------------------

def test_combinator_name():
    out = z.combinator_name("sum", ["If", "Array"])
    assert out["name"] == "sumArrayIf", "порядок в имени фиксирован, а не как передали"
    assert out["combinators"] == ["Array", "If"]
    assert z.combinator_name("uniq", ["State"])["name"] == "uniqState"
    assert z.combinator_name("count", [])["name"] == "count"


def test_combinator_name_validates():
    with pytest.raises(ValueError):
        z.combinator_name("sum", ["Иф"])
    with pytest.raises(ValueError):
        z.combinator_name("uniq", ["State", "Merge"])


def test_agg_if():
    assert z.agg_if([10, 20, 30], [True, False, True]) == pytest.approx(40.0)
    assert z.agg_if([10, 20, 30], [True, False, True], how="count") == 2
    assert z.agg_if([10, 20, 30], [True, False, True], how="avg") == pytest.approx(20.0)
    assert z.agg_if([10, 20], [False, False], how="avg") is None
    with pytest.raises(ValueError):
        z.agg_if([1], [True], how="median")


# --- 12-13. приближённые агрегаты ------------------------------------------

def test_uniq_error_real_numbers():
    """Числа из проекта: uniqExact против uniq на восьми миллионах событий."""
    out = z.uniq_error(2_791_321, 2_799_392)
    assert out["abs_error"] == pytest.approx(8071.0)
    assert out["rel_error"] == pytest.approx(0.00289, abs=1e-5)
    assert out["acceptable"] is True, \
        "0,29% ошибки против выигрыша в 26 раз по времени"


def test_uniq_error_edges():
    assert z.uniq_error(1000, 1200)["acceptable"] is False
    zero = z.uniq_error(0, 0)
    assert zero["rel_error"] is None and zero["acceptable"] is True


def test_uniq_choice():
    assert z.uniq_choice(50_000_000, False, 0.5)["function"] == "uniq"
    assert z.uniq_choice(8_000_000, False, 0.5)["function"] == "uniqCombined"
    assert z.uniq_choice(1000, False, 10)["function"] == "uniqExact"
    exact = z.uniq_choice(50_000_000, True, 10)
    assert exact["function"] == "uniqExact" and exact["approximate"] is False, \
        "нужна точность — объём не имеет значения"


def test_quantile_choice():
    assert z.quantile_choice(1000, False, is_latency=True)["function"] == "quantileTiming"
    assert z.quantile_choice(100, True)["function"] == "quantileExact"
    assert z.quantile_choice(20_000_000, False)["function"] == "quantileTDigest"
    assert z.quantile_choice(1000, False)["function"] == "quantile"


# --- 14-16. воронки --------------------------------------------------------

EV2 = pd.DataFrame({
    "user_id": [1, 1, 1, 1, 2, 2, 3],
    "event_name": ["view", "cart", "checkout", "buy", "view", "cart", "cart"],
    "ts": ["2026-01-01 10:00", "2026-01-01 10:05", "2026-01-01 10:20",
           "2026-01-01 10:30", "2026-01-01 10:00", "2026-01-05 10:00",
           "2026-01-01 10:00"]})
STEPS = ["view", "cart", "checkout", "buy"]


def test_window_funnel_respects_the_window():
    tight = z.window_funnel(EV2, STEPS, 3600)
    assert tight == {1: 4, 2: 1, 3: 0}, \
        ("второй положил в корзину через четыре дня — в час не уложился. "
         "Третий вообще не делал первого шага")
    wide = z.window_funnel(EV2, STEPS, 7 * 86400)
    assert wide[2] == 2, "в недельное окно тот же пользователь укладывается"


def test_window_funnel_skips_foreign_events():
    ev = pd.DataFrame({
        "user_id": [1, 1, 1],
        "event_name": ["view", "search", "cart"],
        "ts": ["2026-01-01 10:00", "2026-01-01 10:01", "2026-01-01 10:02"]})
    assert z.window_funnel(ev, ["view", "cart"], 3600) == {1: 2}, \
        "посторонние события между шагами не мешают"


def test_window_funnel_takes_the_best_attempt():
    ev = pd.DataFrame({
        "user_id": [1, 1, 1],
        "event_name": ["view", "view", "cart"],
        "ts": ["2026-01-01 10:00", "2026-01-01 12:00", "2026-01-01 12:10"]})
    assert z.window_funnel(ev, ["view", "cart"], 3600) == {1: 2}, \
        "первая попытка не уложилась в окно, вторая уложилась"


def test_funnel_levels_to_cumulative():
    t = z.funnel_levels_to_cumulative({1: 4, 2: 1, 3: 0}, 4)
    assert list(t["step"]) == [1, 2, 3, 4]
    assert list(t["users"]) == [2, 1, 1, 1], \
        "накопление с конца: дошедший до 4 посчитан и на 1, 2, 3"
    assert t.loc[1, "from_top"] == pytest.approx(50.0)
    assert t.loc[0, "step_cr"] is None or pd.isna(t.loc[0, "step_cr"])


def test_retention_ch():
    assert z.retention_ch([[True, True, False],
                           [True, False, True],
                           [True, True, True]]) == [2, 1, 2], \
        "знаменатель фиксирован первым условием"
    assert z.retention_ch([]) == []


# --- 17-18. эксплуатация ---------------------------------------------------

def test_ttl_expr():
    out = z.ttl_expr("event_ts", 365, 90, "cold")
    assert out["expression"] == (
        "TTL event_ts + INTERVAL 90 DAY TO VOLUME 'cold', "
        "event_ts + INTERVAL 365 DAY DELETE")
    assert out["moves"] is True
    plain = z.ttl_expr("event_ts", 30)
    assert plain["expression"] == "TTL event_ts + INTERVAL 30 DAY DELETE"
    assert plain["moves"] is False


def test_ttl_expr_validates_order():
    with pytest.raises(ValueError):
        z.ttl_expr("ts", 30, 90, "cold")


def test_mutation_cost():
    out = z.mutation_cost(8_000_000, 18, 1, 8)
    assert out["parts_to_rewrite"] == 18
    assert out["rows_rewritten"] == 8_000_000
    assert out["rewritten_mb"] == pytest.approx(762.94, abs=0.01)
    assert out["changed_share"] == pytest.approx(0.125)
    assert out["asynchronous"] is True
    assert "KILL MUTATION" in out["warning"], \
        "меняем один столбец из восьми, а переписывается всё"
