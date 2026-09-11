"""
Проверка решений тренажёра спринта 19.

Запуск:      make test SPRINT=19
Одна задача: python3 -m pytest sprint-19-airflow/trenazher -q -k catchup
"""

import pandas as pd
import pytest

import zadachi as z


# --- 1. расписание ---------------------------------------------------------

def test_parse_schedule_presets():
    out = z.parse_schedule("@daily")
    assert out["cron"] == "0 0 * * *" and out["recurring"] is True
    assert z.parse_schedule("@hourly")["cron"] == "0 * * * *"
    once = z.parse_schedule("@once")
    assert once["cron"] is None and once["recurring"] is False


def test_parse_schedule_cron_and_manual():
    assert z.parse_schedule("0 3 * * *")["cron"] == "0 3 * * *"
    manual = z.parse_schedule(None)
    assert manual["recurring"] is False and manual["cron"] is None
    with pytest.raises(ValueError):
        z.parse_schedule("0 3 * *")


# --- 2. логическая дата ----------------------------------------------------

def test_logical_vs_actual():
    out = z.logical_vs_actual("2026-06-01", 86400)
    assert out["logical_date"] == pd.Timestamp("2026-06-01")
    assert out["data_interval_start"] == pd.Timestamp("2026-06-01")
    assert out["data_interval_end"] == pd.Timestamp("2026-06-02")
    assert out["runs_at"] == pd.Timestamp("2026-06-02"), \
        ("запуск за первое июня стартует второго: интервал обрабатывается "
         "после того, как закончился")
    assert out["lag_seconds"] == pytest.approx(86400.0)


# --- 3. catchup ------------------------------------------------------------

def test_catchup_runs():
    out = z.catchup_runs("2026-06-01", "2026-06-11", 86400)
    assert out["runs"] == 10
    assert out["dates"][0] == pd.Timestamp("2026-06-01")
    assert out["dates"][-1] == pd.Timestamp("2026-06-10")
    assert out["warning"] == "", "десять запусков — не повод предупреждать"


def test_catchup_false_gives_one_run():
    out = z.catchup_runs("2026-06-01", "2026-06-11", 86400, catchup=False)
    assert out["runs"] == 1
    assert out["dates"] == [pd.Timestamp("2026-06-10")]


def test_catchup_warns_on_a_year_of_backlog():
    out = z.catchup_runs("2026-01-01", "2026-06-11", 86400)
    assert out["runs"] == 161
    assert "161" in out["warning"], \
        ("поставил start_date полгода назад, включил DAG — и он немедленно "
         "создал 161 запуск в один источник")


def test_catchup_edges():
    assert z.catchup_runs("2026-06-11", "2026-06-01", 86400)["runs"] == 0
    capped = z.catchup_runs("2026-01-01", "2026-06-11", 86400, max_runs=5)
    assert capped["runs"] == 5 and capped["capped"] is True


# --- 4. backfill -----------------------------------------------------------

def test_backfill_plan_dag():
    out = z.backfill_plan_dag("2026-06-01", "2026-06-05", 86400, parallelism=2)
    assert out["runs"] == 5
    assert out["waves"] == 3, "пять запусков по два за раз — три волны"
    assert out["logical_dates"][0] == pd.Timestamp("2026-06-01")
    with pytest.raises(ValueError):
        z.backfill_plan_dag("2026-06-05", "2026-06-01", 86400)


# --- 5-6. граф -------------------------------------------------------------

TASKS = ["extract", "clean", "enrich", "mart", "notify"]
DEPS = [("extract", "clean"), ("clean", "enrich"), ("enrich", "mart"),
        ("mart", "notify")]


def test_validate_dag_ok():
    out = z.validate_dag(TASKS, DEPS)
    assert out["valid"] is True and out["has_cycle"] is False
    assert out["isolated"] == [] and out["problems"] == []
    assert out["tasks"] == 5 and out["edges"] == 4


def test_validate_dag_finds_cycle_and_unknown():
    assert z.validate_dag(["a", "b"], [("a", "b"), ("b", "a")])["has_cycle"] is True
    bad = z.validate_dag(["a"], [("a", "b")])
    assert any("неизвестную задачу" in p for p in bad["problems"])
    assert bad["valid"] is False


def test_validate_dag_isolated_is_not_fatal():
    out = z.validate_dag(TASKS + ["orphan"], DEPS)
    assert out["isolated"] == ["orphan"]
    assert out["has_cycle"] is False and out["valid"] is True


FAN = ["extract", "dict_users", "dict_prod", "join", "mart"]
FAN_DEPS = [("extract", "join"), ("dict_users", "join"),
            ("dict_prod", "join"), ("join", "mart")]


def test_dag_levels():
    out = z.dag_levels(FAN, FAN_DEPS)
    assert out["levels"][0] == ["dict_prod", "dict_users", "extract"]
    assert out["levels"][1] == ["join"] and out["levels"][2] == ["mart"]
    assert out["depth"] == 3
    assert out["max_parallel"] == 3, \
        "больше трёх воркеров этот DAG всё равно не займёт"
    with pytest.raises(ValueError):
        z.dag_levels(["a", "b"], [("a", "b"), ("b", "a")])


# --- 7. критический путь ---------------------------------------------------

def test_critical_path():
    out = z.critical_path(FAN, FAN_DEPS,
                          {"extract": 300, "dict_users": 10, "dict_prod": 10,
                           "join": 120, "mart": 60})
    assert out["path"] == ["extract", "join", "mart"]
    assert out["duration"] == pytest.approx(480.0)
    assert out["total_task_time"] == pytest.approx(500.0)
    assert out["speedup_if_parallel"] == pytest.approx(500 / 480)


def test_critical_path_ignores_off_path_work():
    """Ускорять имеет смысл только то, что на критическом пути."""
    slow_dict = z.critical_path(FAN, FAN_DEPS,
                                {"extract": 300, "dict_users": 100,
                                 "dict_prod": 10, "join": 120, "mart": 60})
    assert slow_dict["duration"] == pytest.approx(480.0), \
        "справочник стал вдесятеро медленнее, а DAG не изменился"


# --- 8. скрытые зависимости ------------------------------------------------

def test_find_hidden_deps():
    io = {"a": {"writes": ["s3://stg"]},
          "b": {"reads": ["s3://stg"], "writes": ["ch.mart"]},
          "c": {"reads": ["ch.mart"]}}
    out = z.find_hidden_deps(io, [("a", "b")])
    assert out["n"] == 1 and out["ok"] is False
    assert out["hidden"][0] == {"reader": "c", "writer": "b",
                                "resource": "ch.mart"}


def test_find_hidden_deps_clean():
    io = {"a": {"writes": ["x"]}, "b": {"reads": ["x"]}}
    assert z.find_hidden_deps(io, [("a", "b")])["ok"] is True
    self_read = {"a": {"reads": ["x"], "writes": ["x"]}}
    assert z.find_hidden_deps(self_read, [])["ok"] is True, \
        "задача, читающая свой же ресурс, зависимостью не считается"


# --- 9. повторы ------------------------------------------------------------

def test_retry_delays_exponential():
    out = z.retry_delays(5)
    assert out["delays"] == [60, 120, 240, 480, 960]
    assert out["total_seconds"] == 1860
    assert out["capped"] is False


def test_retry_delays_cap_and_flat():
    capped = z.retry_delays(8)
    assert capped["capped"] is True and max(capped["delays"]) == 3600
    flat = z.retry_delays(3, exponential=False)
    assert flat["delays"] == [60, 60, 60]


# --- 10. сенсоры -----------------------------------------------------------

def test_sensor_config_long_wait():
    out = z.sensor_config("файл в S3", 30 * 60)
    assert out["mode"] == "reschedule", \
        "ждём полчаса — слот воркера освобождаем между проверками"
    assert out["timeout"] == 5400
    assert "таймаут" in out["warning"]


def test_sensor_config_short_wait():
    out = z.sensor_config("партиция", 60)
    assert out["mode"] == "poke"
    assert out["timeout"] == 15 * 60, "минимальный таймаут пятнадцать минут"


# --- 11. SLA ---------------------------------------------------------------

def test_sla_check():
    runs = [{"logical_date": "2026-06-01", "duration": 100},
            {"logical_date": "2026-06-02", "duration": 900}]
    out = z.sla_check(runs, 600)
    assert out["violations"] == 1 and out["share"] == pytest.approx(0.5)
    assert out["worst"] == "2026-06-02"
    assert out["breached_dates"] == ["2026-06-02"]
    empty = z.sla_check([], 600)
    assert empty["runs"] == 0 and empty["worst"] is None


# --- 12. идемпотентность операций ------------------------------------------

def test_task_idempotency():
    assert z.task_idempotency("upsert")["idempotent"] is True
    assert z.task_idempotency("overwrite_partition")["fix"] == ""
    bad = z.task_idempotency("append")
    assert bad["idempotent"] is False and bad["fix"] != ""
    assert z.task_idempotency("send_email")["idempotent"] is False, \
        "retry задачи с письмом отправит письмо дважды"
    with pytest.raises(ValueError):
        z.task_idempotency("merge_into")


# --- 13. секреты -----------------------------------------------------------

DIRTY = '''conn = "postgres://analyst:secret123@db:5432/casino"
password = "hunter2"
x = 1
'''


def test_secret_scan_finds():
    out = z.secret_scan(DIRTY)
    assert out["clean"] is False and out["n"] == 2
    assert {f["rule"] for f in out["findings"]} == {"password", "conn_uri"}
    assert out["advice"] != ""


def test_secret_scan_clean_code():
    ok = z.secret_scan("token = Variable.get('api_token')\nconn_id = 'ch_default'")
    assert ok["clean"] is True and ok["advice"] == ""


def test_secret_scan_rule_order():
    rules = [f["rule"] for f in z.secret_scan(DIRTY)["findings"]]
    order = [r[0] for r in z.SECRET_PATTERNS]
    assert rules == sorted(rules, key=order.index)


# --- 14. connection --------------------------------------------------------

def test_connection_uri():
    out = z.connection_uri("postgres", "db", 5432, "analyst", "p@ss", "casino")
    assert out["uri"] == "postgres://analyst:p%40ss@db:5432/casino", \
        "спецсимволы пароля экранируются, иначе @ разорвёт URI"
    assert "***" in out["masked"] and "p%40ss" not in out["masked"]


def test_connection_uri_optional_parts():
    bare = z.connection_uri("http", "api.example.com", 80)
    assert bare["uri"] == "http://api.example.com:80"
    with_extra = z.connection_uri("clickhouse", "ch", 8123, extra={"secure": "false"})
    assert with_extra["uri"].endswith("?secure=false")


# --- 15. шаблоны -----------------------------------------------------------

def test_render_template():
    out = z.render_template("s3://raw/events/dt={{ ds }}/", {"ds": "2026-06-01"})
    assert out == "s3://raw/events/dt=2026-06-01/"
    assert z.render_template("{{a}}-{{ b }}", {"a": 1, "b": 2}) == "1-2"


def test_render_template_is_strict():
    with pytest.raises(KeyError):
        z.render_template("s3://raw/dt={{ ds }}/", {})
    with pytest.raises(KeyError):
        z.render_template("{{ a }}{{ b }}{{ a }}", {})


# --- 16. история падений ---------------------------------------------------

def test_failure_summary():
    runs = [{"task": "extract", "state": "success"},
            {"task": "extract", "state": "failed"},
            {"task": "extract", "state": "failed"},
            {"task": "mart", "state": "success"}]
    out = z.failure_summary(runs)
    assert out["total_runs"] == 4 and out["total_failed"] == 2
    assert out["worst"] == "extract"
    assert out["tasks"][0]["failure_rate"] == pytest.approx(2 / 3)


def test_failure_summary_sorts_by_rate_not_count():
    runs = ([{"task": "noisy", "state": "failed"}] * 5
            + [{"task": "noisy", "state": "success"}] * 995
            + [{"task": "broken", "state": "failed"}] * 3
            + [{"task": "broken", "state": "success"}])
    out = z.failure_summary(runs)
    assert out["worst"] == "broken", \
        ("три падения из четырёх важнее пяти из тысячи — смотрим на долю, "
         "а не на счётчик")


# --- 17. пулы --------------------------------------------------------------

def test_pool_plan():
    out = z.pool_plan(10, 4, 60)
    assert out["waves"] == 3 and out["queued"] == 6
    assert out["wall_clock_seconds"] == pytest.approx(180.0)
    assert out["enough"] is False
    assert z.pool_plan(3, 4)["enough"] is True
    with pytest.raises(ValueError):
        z.pool_plan(10, 0)


# --- 18. ревью конфигурации ------------------------------------------------

def test_dag_review_finds_everything():
    out = z.dag_review({"catchup": True, "start_date": "2026-01-01",
                        "sensor": True})
    assert out["ok"] is False and out["n"] == 4
    joined = " ".join(out["problems"])
    assert "catchup" in joined and "retries" in joined
    assert "уведомлен" in joined and "таймаут" in joined


def test_dag_review_clean():
    out = z.dag_review({"schedule": "@daily", "start_date": "2026-06-01",
                        "retries": 3, "on_failure_callback": True})
    assert out["ok"] is True and out["problems"] == []


def test_dag_review_depends_on_past_with_catchup():
    out = z.dag_review({"start_date": "2026-01-01", "catchup": True,
                        "depends_on_past": True, "retries": 2,
                        "email_on_failure": True})
    assert any("depends_on_past" in p for p in out["problems"])
