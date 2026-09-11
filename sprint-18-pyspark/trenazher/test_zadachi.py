"""
Проверка решений тренажёра спринта 18.

Запуск:      make test SPRINT=18
Одна задача: python3 -m pytest sprint-18-pyspark/trenazher -q -k shuffle
"""

import numpy as np
import pandas as pd
import pytest

import zadachi as z


PIPELINE = ["read", "filter", "withColumn", "groupBy", "agg", "join",
            "orderBy", "write"]


# --- 1. действия и трансформации -------------------------------------------

def test_is_action():
    a = z.is_action("collect")
    assert a["kind"] == "action" and a["triggers_execution"] is True
    f = z.is_action("filter")
    assert f["kind"] == "transformation" and f["wide"] is False
    assert f["triggers_execution"] is False
    g = z.is_action("groupBy")
    assert g["wide"] is True
    with pytest.raises(ValueError):
        z.is_action("magic")


def test_is_action_write_is_an_action():
    assert z.is_action("write")["triggers_execution"] is True
    assert z.is_action("toPandas")["triggers_execution"] is True
    assert z.is_action("withColumn")["triggers_execution"] is False, \
        "трансформация только дописывает шаг в план"


# --- 2-4. shuffle и стадии -------------------------------------------------

def test_find_shuffles():
    s = z.find_shuffles(PIPELINE)
    assert [(f["position"], f["op"]) for f in s] == \
        [(3, "groupBy"), (5, "join"), (6, "orderBy")]
    assert all(f["reason"] for f in s)
    assert z.find_shuffles(["filter", "select", "withColumn"]) == []


def test_count_stages():
    out = z.count_stages(PIPELINE)
    assert out["shuffles"] == 3
    assert out["stages"] == 4, "стадий на одну больше, чем shuffle-ов"
    assert out["executes"] is True and out["note"] == ""


def test_count_stages_without_action():
    out = z.count_stages(["filter", "groupBy"])
    assert out["executes"] is False and out["note"] != "", \
        "план построен, но без действия ничего не выполнится"
    assert z.count_stages([])["stages"] == 0


def test_build_dag_agrees_with_count_stages():
    dag = z.build_dag(PIPELINE)
    assert dag["stages"][0] == ["read", "filter", "withColumn", "groupBy"], \
        "широкая трансформация входит в ту стадию, которую закрывает"
    assert dag["stages"][1] == ["agg", "join"]
    assert dag["stages"][2] == ["orderBy"]
    assert dag["stages"][3] == [], \
        "после последнего shuffle открывается стадия записи результата"
    assert dag["n_stages"] == z.count_stages(PIPELINE)["stages"]
    assert dag["actions"] == ["write"] and dag["lazy_until"] == "write"


# --- 5. явная схема --------------------------------------------------------

def test_schema_from_spec():
    out = z.schema_from_spec({"user_id": ("long", False),
                              "event_ts": ("timestamp", False),
                              "revenue": ("decimal", True)})
    assert out.startswith("StructType([") and out.endswith("])")
    assert '    StructField("user_id", LongType(), False),' in out
    assert '    StructField("revenue", DecimalType(10, 2), True),' in out
    assert out.splitlines()[3].endswith(","), "запятая после последнего поля тоже"
    with pytest.raises(ValueError):
        z.schema_from_spec({"x": ("uuid", True)})


# --- 6. риски inference ----------------------------------------------------

def test_inference_risks_leading_zeros():
    out = z.inference_risks(["001", "002", "010"], "zip")
    assert out["safe"] is False
    assert any("нул" in r for r in out["risks"]), \
        "индекс 001 станет числом 1, и данные потеряны навсегда"


def test_inference_risks_money_as_float():
    out = z.inference_risks(["1.5", "2.25", "3.0"], "price")
    assert out["guessed"] == "DoubleType()"
    assert any("точност" in r or "Decimal" in r for r in out["risks"])


def test_inference_risks_mixed_column():
    out = z.inference_risks(["1", "2", "abc"], "mixed")
    assert out["guessed"] == "StringType()"
    assert any("выборк" in r for r in out["risks"]), \
        "завтра приедет файл без букв — и тип поменяется"


def test_inference_risks_nulls_and_empty():
    assert any("пропуск" in r for r in z.inference_risks([1, 2, None, 4], "n")["risks"])
    empty = z.inference_risks([None, ""], "x")
    assert empty["safe"] is False and empty["guessed"] == "StringType()"


# --- 7-8. форматы и раскладка ----------------------------------------------

def test_format_choice():
    big = z.format_choice(8_000_000, 3, 8)
    assert big["format"] == "parquet" and big["columnar"] is True
    assert "3" in big["reason"] and "8" in big["reason"]
    assert z.format_choice(500, 3, 4)["format"] == "csv"
    assert z.format_choice(8_000_000, 3, 8, need_human_readable=True)["format"] == "csv"


def test_parquet_layout_too_many_partitions():
    out = z.parquet_layout(8_000_000, 60, ["dt", "country"],
                           {"dt": 540, "country": 6})
    assert out["partitions"] == 3240
    assert out["mb_per_partition"] < 1
    assert out["small_files_problem"] is True
    assert out["path_template"] == "dt=<dt>/country=<country>"


def test_parquet_layout_reasonable():
    out = z.parquet_layout(8_000_000, 60, ["dt"], {"dt": 18})
    assert out["partitions"] == 18
    assert out["mb_per_partition"] == pytest.approx(25.43, abs=0.01)
    assert out["small_files_problem"] is False
    assert out["files"] == 18


# --- 9. broadcast ----------------------------------------------------------

def test_broadcast_decision():
    yes = z.broadcast_decision(5000, 3)
    assert yes["broadcast"] is True and yes["side"] == "right"
    assert yes["strategy"] == "BroadcastHashJoin"
    no = z.broadcast_decision(5000, 300)
    assert no["broadcast"] is False and no["side"] is None
    assert no["strategy"] == "SortMergeJoin"


def test_broadcast_picks_the_smaller_side():
    out = z.broadcast_decision(2, 5000)
    assert out["broadcast"] is True and out["side"] == "left"
    assert out["small_mb"] == 2 and out["large_mb"] == 5000


# --- 10-11. партиции -------------------------------------------------------

def test_partition_plan_coalesce_vs_repartition():
    down = z.partition_plan(200, 20, 8_000_000)
    assert down["op"] == "coalesce" and down["causes_shuffle"] is False
    up = z.partition_plan(8, 64, 8_000_000)
    assert up["op"] == "repartition" and up["causes_shuffle"] is True, \
        "увеличить число партиций без перемешивания нельзя"


def test_partition_plan_recommends():
    out = z.partition_plan(8, None, 8_000_000)
    assert out["recommended"] == 8
    assert z.partition_plan(4, None, 100_000_000, cores=8)["recommended"] == 100
    assert out["op"] == "ничего"


def test_skew_check():
    bad = z.skew_check([100, 120, 110, 2000])
    assert bad["skewed"] is True
    assert bad["max_partition"] == 3
    assert bad["ratio"] == pytest.approx(3.433, abs=0.01)
    good = z.skew_check([100, 120, 110, 105])
    assert good["skewed"] is False
    assert z.skew_check([]) is None


# --- 12-13. кэш и стратегия соединения -------------------------------------

def test_cache_decision():
    assert z.cache_decision(3, 500, 4000)["cache"] is True
    assert z.cache_decision(1, 100, 4000)["cache"] is False, \
        "используется один раз — кэш только займёт память"
    assert z.cache_decision(3, 500, 4000, is_expensive=False)["cache"] is False


def test_cache_decision_does_not_fit():
    out = z.cache_decision(3, 5000, 4000)
    assert out["cache"] is False and out["fits"] is False
    assert "alternative" in out, \
        "кэш, не влезающий в память, вытесняет сам себя"


def test_join_strategy():
    assert z.join_strategy(5000, 3)["strategy"] == "BroadcastHashJoin"
    assert z.join_strategy(5000, 3)["shuffle"] is False
    big = z.join_strategy(5000, 4000)
    assert big["strategy"] == "SortMergeJoin" and big["shuffle"] is True
    sorted_ = z.join_strategy(5000, 4000, join_key_sorted=True)
    assert sorted_["shuffle"] is False


# --- 14-15. режимы записи --------------------------------------------------

def test_write_mode():
    assert z.write_mode("full_reload")["mode"] == "overwrite"
    assert z.write_mode("first_write")["mode"] == "errorifexists"
    assert z.write_mode("skip_if_exists")["mode"] == "ignore"
    with pytest.raises(ValueError):
        z.write_mode("upsert")


def test_write_mode_warnings_are_the_point():
    inc = z.write_mode("incremental")
    assert inc["mode"] == "append" and inc["idempotent"] is False
    assert "задво" in inc["warning"]
    part = z.write_mode("reprocess_partition")
    assert "dynamic" in part["warning"], \
        "без partitionOverwriteMode=dynamic overwrite снесёт всю таблицу"


def test_partitioned_write_paths():
    out = z.partitioned_write_paths("s3a://lake/mart/",
                                    [{"dt": "2026-06-02"}, {"dt": "2026-06-01"},
                                     {"dt": "2026-06-01"}])
    assert out["paths"] == ["s3a://lake/mart/dt=2026-06-01",
                            "s3a://lake/mart/dt=2026-06-02"]
    assert out["n_paths"] == 2 and out["warning"] == ""
    static = z.partitioned_write_paths("s3a://lake/mart", [{"dt": "2026-06-01"}],
                                       dynamic=False)
    assert static["overwrites_everything"] is True and static["warning"] != ""


# --- 16-17. файлы и driver -------------------------------------------------

def test_small_files_check():
    bad = z.small_files_check(3240, 500)
    assert bad["ok"] is False
    assert bad["avg_file_mb"] == pytest.approx(0.154, abs=0.001)
    assert "coalesce" in bad["advice"]
    good = z.small_files_check(40, 5000)
    assert good["ok"] is True and good["problems"] == []


def test_small_files_check_too_many():
    out = z.small_files_check(50_000, 5_000_000)
    assert out["ok"] is False
    assert any("метаданны" in p for p in out["problems"])


def test_driver_memory_risk_row_count_matters():
    out = z.driver_memory_risk(8_000_000, 60, 2048)
    assert out["safe"] is False and out["too_many_rows"] is True
    assert "8000000" in out["advice"]
    assert out["needed_mb"] == pytest.approx(1373.29, abs=0.1), \
        "в памяти driver строка занимает втрое больше, чем в Parquet"


def test_driver_memory_risk_small_is_fine():
    out = z.driver_memory_risk(1000, 60, 2048, op="toPandas")
    assert out["safe"] is True
    plain = z.driver_memory_risk(1000, 60, 2048)
    assert out["needed_mb"] == pytest.approx(plain["needed_mb"] * 2), \
        "toPandas держит и JVM-, и Python-копию"


# --- 18. идемпотентность ---------------------------------------------------

def test_pipeline_idempotent_append_duplicates():
    out = z.pipeline_idempotent(["a", "b"], ["b", "c"], "append")
    assert out["idempotent"] is False
    assert out["duplicated"] == ["b"] and out["added"] == ["c"]


def test_pipeline_idempotent_dynamic_is_safe():
    out = z.pipeline_idempotent(["a", "b"], ["b", "c"], "overwrite_dynamic")
    assert out["idempotent"] is True
    assert out["duplicated"] == [] and out["lost"] == []


def test_pipeline_idempotent_static_loses_history():
    out = z.pipeline_idempotent(["a", "b"], ["b", "c"], "overwrite_static")
    assert out["idempotent"] is True
    assert out["lost"] == ["a"], \
        ("статический overwrite сносит партиции, которых нет в новых "
         "данных. Тихая потеря, которую замечают через неделю")
    with pytest.raises(ValueError):
        z.pipeline_idempotent([], [], "upsert")
