"""
Проверка решений тренажёра спринта 13.

Запуск:      make test SPRINT=13
Одна задача: python3 -m pytest sprint-13-metriki/trenazher -q -k retention

Тесты открыты для чтения. Это требования, а не ответы: они говорят,
какое число правильное, но не говорят, как его получить.
"""

import numpy as np
import pandas as pd
import pytest

import zadachi as z


# --- общие данные ----------------------------------------------------------
#
# Десять пользователей трёх когорт. Девятый и десятый не сделали ничего
# ни разу — это не пропуск в данных, это ушедшие пользователи, и почти
# каждая задача ниже проверяет, что они не потерялись.

USERS = pd.DataFrame({
    "user_id": list(range(1, 11)),
    "reg_date": ["2026-01-05"] * 5 + ["2026-02-10"] * 3 + ["2026-03-01"] * 2,
})

_ACT = {1: [0, 1, 3, 7, 30], 2: [0, 1, 2], 3: [0, 7], 4: [0], 5: [0, 1, 7, 14],
        6: [0, 1], 7: [0, 3, 7], 8: [0], 9: [], 10: []}
_REG = dict(zip(USERS["user_id"], pd.to_datetime(USERS["reg_date"])))
EVENTS = pd.DataFrame([
    {"user_id": u, "ts": (_REG[u] + pd.Timedelta(days=d)).strftime("%Y-%m-%d")}
    for u, days in _ACT.items() for d in days
])

ORDERS = pd.DataFrame([
    {"user_id": 1, "ts": "2026-01-06", "revenue": 100.0},
    {"user_id": 1, "ts": "2026-02-04", "revenue": 50.0},
    {"user_id": 2, "ts": "2026-01-07", "revenue": 30.0},
    {"user_id": 5, "ts": "2026-01-19", "revenue": 20.0},
    {"user_id": 6, "ts": "2026-02-11", "revenue": 60.0},
])


def _t(day, hh, mm=0):
    return f"2026-05-{day:02d} {hh:02d}:{mm:02d}:00"


# Воронка visit → signup → first_order → repeat_order.
# Шестой зарегистрировался ДО первого визита (пришёл по ретаргету со
# старого аккаунта), седьмой заказал, не регистрируясь. Открытая воронка
# засчитает обоим шаги, закрытая — нет.
FUNNEL = pd.DataFrame([
    (1, "visit", _t(1, 10, 0), "ios"),
    (1, "signup", _t(1, 10, 5), "ios"),
    (1, "first_order", _t(1, 11, 0), "ios"),
    (1, "repeat_order", _t(3, 12, 0), "ios"),
    (2, "visit", _t(1, 10, 0), "android"),
    (2, "signup", _t(1, 10, 20), "android"),
    (2, "first_order", _t(2, 9, 0), "android"),
    (3, "visit", _t(1, 11, 0), "ios"),
    (3, "signup", _t(1, 15, 0), "ios"),
    (4, "visit", _t(1, 12, 0), "android"),
    (5, "visit", _t(1, 13, 0), "android"),
    (6, "signup", _t(1, 9, 0), "ios"),
    (6, "visit", _t(1, 10, 0), "ios"),
    (7, "visit", _t(1, 14, 0), "android"),
    (7, "first_order", _t(1, 16, 0), "android"),
    (8, "visit", _t(2, 10, 0), "ios"),
    (8, "signup", _t(2, 10, 30), "ios"),
    (8, "first_order", _t(2, 14, 0), "ios"),
    (8, "repeat_order", _t(6, 10, 0), "ios"),
    (9, "visit", _t(2, 11, 0), "android"),
    (9, "signup", _t(4, 11, 0), "android"),
    (10, "visit", _t(2, 12, 0), "ios"),
], columns=["user_id", "event_name", "ts", "platform"])

STEPS = ["visit", "signup", "first_order", "repeat_order"]


# --- 1. DAU / WAU / MAU ----------------------------------------------------

def test_dau_wau_mau():
    out = z.dau_wau_mau(FUNNEL[["user_id", "ts"]])
    assert set(out) >= {"dau", "wau", "mau", "sticky_dau_mau", "sticky_dau_wau"}
    assert out["mau"] == pytest.approx(10.0), \
        "все десять активны в мае — MAU равен десяти, а не сумме дневных"
    assert out["dau"] == pytest.approx(2.8, abs=1e-9)
    assert out["wau"] == pytest.approx(6.0)
    assert out["sticky_dau_mau"] == pytest.approx(0.28, abs=1e-9)
    assert out["sticky_dau_wau"] == pytest.approx(0.466667, abs=1e-5)


def test_dau_ignores_empty_days():
    """DAU считается по дням, присутствующим в данных."""
    two = pd.DataFrame({"user_id": [1, 2, 3, 4],
                        "ts": ["2026-05-01", "2026-05-01",
                               "2026-05-10", "2026-05-10"]})
    out = z.dau_wau_mau(two)
    assert out["dau"] == pytest.approx(2.0), \
        ("два дня по два пользователя дают DAU 2, хотя между ними восемь "
         "пустых суток. Календарный DAU за период был бы 0,4 — "
         "разница в пять раз, и она не видна из результата")
    assert out["mau"] == pytest.approx(4.0)


# --- 2. активные за окно ---------------------------------------------------

def test_active_users_window():
    d1 = z.active_users(FUNNEL, "2026-05-01")
    assert d1["users"] == 7 and d1["events"] == 13
    assert d1["window"] == 1
    assert str(d1["day"]) == "2026-05-01"

    w7 = z.active_users(FUNNEL, "2026-05-06", window=7)
    assert w7["users"] == 10, "окно [30 апреля, 6 мая] накрывает всех"
    assert w7["events"] == 22


def test_active_users_definition_changes_the_number():
    narrow = z.active_users(FUNNEL, "2026-05-06", window=7,
                            name_col="event_name",
                            active_events=["first_order", "repeat_order"])
    assert narrow["users"] == 4, \
        ("тот же день, то же окно, другое определение активности — "
         "4 против 10. Метрика без определения активности бессмысленна")
    assert narrow["events"] == 6


def test_active_users_requires_name_col():
    with pytest.raises(ValueError):
        z.active_users(FUNNEL, "2026-05-06", active_events=["visit"])


# --- 3. три retention ------------------------------------------------------

def test_retention_nday():
    out = z.retention_nday(USERS, EVENTS, 1)
    assert set(out) >= {"n", "cohort_size", "retained", "retention"}
    assert out["cohort_size"] == 10, \
        "девятый и десятый не сделали ничего, но в знаменатель обязаны попасть"
    assert out["retained"] == 4
    assert out["retention"] == pytest.approx(0.4)

    d7 = z.retention_nday(USERS, EVENTS, 7)
    assert d7["retained"] == 4 and d7["retention"] == pytest.approx(0.4)


def test_retention_nday_is_not_monotone():
    curve = {d: z.retention_nday(USERS, EVENTS, d)["retained"] for d in [3, 4, 7]}
    assert curve == {3: 2, 4: 0, 7: 4}, \
        ("N-day проваливается в ноль на дне 4 и снова растёт на дне 7. "
         "Это не ошибка: люди возвращаются по неделям")


def test_rolling_retention():
    r7 = z.rolling_retention(USERS, EVENTS, 7)
    assert r7["retained"] == 4 and r7["retention"] == pytest.approx(0.4)
    r8 = z.rolling_retention(USERS, EVENTS, 8)
    assert r8["retained"] == 2 and r8["retention"] == pytest.approx(0.2)
    assert all(z.rolling_retention(USERS, EVENTS, n)["retained"]
               >= z.rolling_retention(USERS, EVENTS, n + 1)["retained"]
               for n in range(0, 30)), "rolling обязан быть невозрастающим"


def test_unbounded_retention():
    out = z.unbounded_retention(USERS, EVENTS, 7)
    assert out["retained"] == 6 and out["retention"] == pytest.approx(0.6)
    assert z.unbounded_retention(USERS, EVENTS, 0)["retained"] == 0, \
        "интервал [1, 0] пуст: день регистрации в unbounded не входит"


def test_three_definitions_disagree():
    """Одни данные, один день, три определения — три разных числа."""
    nday = z.retention_nday(USERS, EVENTS, 7)["retention"]
    unb = z.unbounded_retention(USERS, EVENTS, 7)["retention"]
    roll = z.rolling_retention(USERS, EVENTS, 8)["retention"]
    assert (nday, unb, roll) == pytest.approx((0.4, 0.6, 0.2)), \
        ("40%, 60% и 20% — разброс втрое. Число без названия определения "
         "не значит ничего")


# --- 4. кривая удержания ---------------------------------------------------

def test_retention_curve():
    c = z.retention_curve(USERS, EVENTS, max_day=7)
    assert list(c.columns) >= ["day_n", "retained", "retention"]
    assert len(c) == 8, "дни от 0 до 7 включительно"
    assert list(c["day_n"]) == list(range(8))
    assert list(c["retained"]) == [8, 4, 1, 2, 0, 0, 0, 4], \
        "дни 4, 5 и 6 пустые — но строки для них должны быть"
    assert c.loc[0, "retention"] == pytest.approx(0.8)


# --- 5. когортная матрица --------------------------------------------------

def test_cohort_matrix():
    m = z.cohort_matrix(USERS, EVENTS, max_period=2)
    assert list(m.columns) == [0, 1, 2]
    assert len(m) == 3, "три когорты регистрации — три строки"
    assert list(m.iloc[0]) == [100.0, 20.0, 0.0]
    assert list(m.iloc[1]) == [100.0, 0.0, 0.0]


def test_cohort_matrix_keeps_dead_cohort():
    m = z.cohort_matrix(USERS, EVENTS, max_period=2)
    dead = m.iloc[2]
    assert not dead.isna().any(), \
        ("мартовская когорта не сделала ничего. Строка обязана быть "
         "нулевой, а не из NaN: мёртвая когорта — самый важный сигнал "
         "в этой таблице")
    assert list(dead) == [0.0, 0.0, 0.0]


# --- 6. воронки ------------------------------------------------------------

def test_funnel_open():
    f = z.funnel_open(FUNNEL, STEPS)
    assert list(f["step"]) == STEPS
    assert list(f["users"]) == [10, 6, 4, 2]
    assert f.loc[1, "step_cr"] == pytest.approx(60.0)
    assert f.loc[2, "step_cr"] == pytest.approx(66.67)
    assert f.loc[3, "from_top"] == pytest.approx(20.0)
    assert f.loc[0, "step_cr"] is None or pd.isna(f.loc[0, "step_cr"])


def test_funnel_closed():
    f = z.funnel_closed(FUNNEL, STEPS)
    assert list(f["users"]) == [10, 5, 3, 2]
    assert f.loc[1, "step_cr"] == pytest.approx(50.0)
    assert f.loc[2, "from_top"] == pytest.approx(30.0)


def test_open_and_closed_disagree():
    o = z.funnel_open(FUNNEL, STEPS)["users"].tolist()
    c = z.funnel_closed(FUNNEL, STEPS)["users"].tolist()
    assert o == [10, 6, 4, 2] and c == [10, 5, 3, 2]
    assert all(a >= b for a, b in zip(o, c)), \
        "закрытая воронка не может быть выше открытой"
    assert o[1] - c[1] == 1 and o[2] - c[2] == 1, \
        ("расхождение — это не погрешность, а измерение: два человека "
         "прошли шаги не в том порядке, который нарисовал продакт")


def test_funnel_closed_handles_missing_step():
    only_android = FUNNEL[FUNNEL["platform"] == "android"]
    f = z.funnel_closed(only_android, STEPS)
    assert list(f["users"]) == [5, 2, 1, 0], \
        "повторных заказов у android нет вовсе — это ноль, а не исключение"


def test_funnel_by_segment():
    f = z.funnel_by_segment(FUNNEL, STEPS, "platform")
    assert list(f.columns) == ["segment", "step", "users", "step_cr", "from_top"]
    assert len(f) == 8
    assert list(f["segment"]) == ["android"] * 4 + ["ios"] * 4
    assert list(f["step"][:4]) == STEPS, "внутри сегмента порядок шагов сохраняется"
    android = f[f["segment"] == "android"]["users"].tolist()
    ios = f[f["segment"] == "ios"]["users"].tolist()
    assert android == [5, 2, 1, 0]
    assert ios == [5, 3, 2, 2]
    assert f[f["segment"] == "ios"]["from_top"].iloc[3] == pytest.approx(40.0)
    assert f[f["segment"] == "android"]["from_top"].iloc[3] == pytest.approx(0.0), \
        ("общая воронка показала 20% до повторного заказа. В разрезе — "
         "40% и 0%. Узкое место видно только здесь")


# --- 7. время до конверсии -------------------------------------------------

def test_time_to_convert():
    out = z.time_to_convert(FUNNEL, "visit", "first_order")
    assert set(out) >= {"n", "median_hours", "mean_hours", "p90_hours"}
    assert out["n"] == 4
    assert out["median_hours"] == pytest.approx(3.0)
    assert out["mean_hours"] == pytest.approx(7.5)
    assert out["p90_hours"] == pytest.approx(17.3, abs=1e-6)
    assert out["mean_hours"] > 2 * out["median_hours"], \
        "среднее вдвое выше медианы — отчитываться средним здесь нельзя"


def test_time_to_convert_drops_reversed_pairs():
    out = z.time_to_convert(FUNNEL, "visit", "signup")
    assert out["n"] == 5, \
        ("у шестого регистрация раньше визита. Это не отрицательное "
         "время, это другой сценарий, и он выбрасывается")
    assert z.time_to_convert(FUNNEL, "repeat_order", "visit") is None


# --- 8. деньги -------------------------------------------------------------

def test_arpu_arppu():
    out = z.arpu_arppu(10, ORDERS)
    assert out["revenue"] == pytest.approx(260.0)
    assert out["payers"] == 4
    assert out["arpu"] == pytest.approx(26.0)
    assert out["arppu"] == pytest.approx(65.0)
    assert out["payer_share"] == pytest.approx(0.4)
    assert out["avg_order"] == pytest.approx(52.0), \
        "средний чек на заказ (5 заказов), а не на платящего"
    assert out["arpu"] == pytest.approx(out["arppu"] * out["payer_share"]), \
        "ARPU = ARPPU × доля платящих — бесплатный санити-чек"


def test_avg_check_tail():
    vals = [10., 12., 14., 15., 16., 18., 20., 20., 22., 25.,
            25., 28., 30., 32., 35., 40., 45., 50., 60., 1000.]
    out = z.avg_check(pd.DataFrame({"revenue": vals}))
    assert out["n"] == 20
    assert out["mean"] == pytest.approx(75.85)
    assert out["median"] == pytest.approx(25.0)
    assert out["p90"] == pytest.approx(51.0, abs=1e-6)
    assert out["skew_ratio"] == pytest.approx(3.034, abs=1e-3)
    assert out["top1pct_revenue_share"] == pytest.approx(0.65920, abs=1e-4), \
        "один заказ из двадцати дал две трети выручки"
    assert z.avg_check(pd.DataFrame({"revenue": []})) is None


def test_avg_check_ignores_non_numeric():
    out = z.avg_check(pd.DataFrame({"revenue": [10.0, None, 30.0, "нет"]}))
    assert out["n"] == 2 and out["mean"] == pytest.approx(20.0)


def test_ggr_ngr():
    bets = pd.DataFrame({"bet": [100., 200., 50., 300.],
                         "win": [80., 150., 60., 200.],
                         "bonus": [10., 0., 0., 5.]})
    plain = z.ggr_ngr(bets)
    assert plain["turnover"] == pytest.approx(650.0)
    assert plain["ggr"] == pytest.approx(160.0)
    assert plain["ngr"] == pytest.approx(160.0), "без бонусов NGR равен GGR"
    assert plain["hold_pct"] == pytest.approx(24.6154, abs=1e-3)
    assert plain["rtp_pct"] == pytest.approx(75.3846, abs=1e-3)
    assert plain["hold_pct"] + plain["rtp_pct"] == pytest.approx(100.0)

    full = z.ggr_ngr(bets, bonus_col="bonus", fees=12.5)
    assert full["bonus"] == pytest.approx(15.0)
    assert full["ngr"] == pytest.approx(132.5)
    assert full["turnover"] / full["ngr"] > 4, \
        ("оборот 650 против выручки 132,5. Показать оборот как выручку — "
         "завысить бизнес впятеро")


def test_ltv_by_cohort():
    m = z.ltv_by_cohort(USERS, ORDERS, max_period=2)
    assert list(m.columns) == [0, 1, 2]
    assert list(m.iloc[0]) == [30.0, 40.0, 40.0], \
        "значения накапливаются: столбец 1 включает столбец 0"
    assert list(m.iloc[1]) == [20.0, 20.0, 20.0]
    assert m.iloc[0, 0] == pytest.approx(150.0 / 5), \
        "делим на всю когорту, включая неплативших. Иначе это ARPPU"


def test_ltv_by_cohort_zero_not_nan():
    m = z.ltv_by_cohort(USERS, ORDERS, max_period=2)
    assert not m.isna().any().any(), \
        ("мартовская когорта ничего не купила. Накопительная сумма по "
         "пустой строке даёт NaN — это надо закрыть явно")
    assert list(m.iloc[2]) == [0.0, 0.0, 0.0]


def test_unit_economics():
    good = z.unit_economics(50, 80)
    assert good["ltv_cac"] == pytest.approx(1.6)
    assert good["payback_periods"] == pytest.approx(0.625)
    assert good["profitable"] is True

    awful = z.unit_economics(779, 52)
    assert awful["ltv_cac"] == pytest.approx(0.0668, abs=1e-4)
    assert awful["payback_periods"] == pytest.approx(14.98, abs=1e-2)
    assert awful["profitable"] is False


def test_unit_economics_margin_flips_the_verdict():
    by_revenue = z.unit_economics(57, 120)
    by_margin = z.unit_economics(57, 120, margin=0.35)
    assert by_revenue["profitable"] is True
    assert by_margin["profitable"] is False, \
        ("по выручке канал прибылен, по марже — нет. Юнит-экономика "
         "по выручке доказывает что угодно")
    assert by_margin["ltv_cac"] == pytest.approx(0.7368, abs=1e-4)


def test_unit_economics_free_traffic():
    org = z.unit_economics(0, 30)
    assert org["ltv_cac"] is None and org["payback_periods"] is None
    assert org["profitable"] is True


# --- 9. контроль -----------------------------------------------------------

def test_sanity_check():
    ok = z.sanity_check([100.0, 200.0, 300.0], 600)
    assert ok["ok"] is True and ok["diff"] == pytest.approx(0.0)
    bad = z.sanity_check([100.0, 200.0, 280.0], 600)
    assert bad["ok"] is False and bad["diff"] == pytest.approx(-20.0)
    assert z.sanity_check([100.0, 200.0, 302.0], 600)["ok"] is True, \
        "допуск относительный: 2 из 600 — это 0,33%, в пределах одного процента"


def test_metric_consistency_ok():
    out = z.metric_consistency({
        "users": 1000, "payers": 250, "arpu": 26.0, "arppu": 104.0,
        "revenue": 26000.0, "conversion": 0.25,
        "dau": 120, "wau": 400, "mau": 800})
    assert out["ok"] is True and out["problems"] == []


def test_metric_consistency_catches_impossible_report():
    out = z.metric_consistency({
        "users": 1000, "payers": 1200, "arpu": 30.0, "arppu": 20.0,
        "revenue": 26000.0, "conversion": 1.2,
        "dau": 900, "wau": 400, "mau": 800})
    assert out["ok"] is False
    assert out["problems"] == ["payers > users", "arppu < arpu",
                               "conversion вне [0, 1]", "dau > mau",
                               "dau > wau", "revenue != arpu * users"]


def test_metric_consistency_partial_report():
    out = z.metric_consistency({"users": 100, "payers": 20})
    assert out["ok"] is True, "отсутствующие ключи не проверяются"
