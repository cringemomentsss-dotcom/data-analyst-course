"""
Проверка решений тренажёра спринта 14.

Запуск:      make test SPRINT=14
Одна задача: python3 -m pytest sprint-14-unit-ekonomika/trenazher -q -k payback

Тесты открыты для чтения: это требования, а не ответы.
"""

import numpy as np
import pandas as pd
import pytest

import zadachi as z


# --- 1. P&L юнита ----------------------------------------------------------

def test_unit_pnl():
    out = z.unit_pnl(120.0, 78.0, 57.0)
    assert out["gross_margin"] == pytest.approx(42.0)
    assert out["gross_margin_pct"] == pytest.approx(35.0)
    assert out["contribution_margin"] == pytest.approx(-15.0)
    assert out["profitable"] is False, \
        ("валовая маржа 35% выглядит здорово, но клиент стоит 57 при "
         "марже 42. Это убыточный бизнес, а не прибыльный с проблемой "
         "в маркетинге")


def test_unit_pnl_scales_to_units():
    one = z.unit_pnl(120.0, 78.0, 57.0)
    ten = z.unit_pnl(1200.0, 780.0, 570.0, units=10)
    assert ten["contribution_per_unit"] == pytest.approx(one["contribution_per_unit"])
    assert ten["gross_margin_pct"] == pytest.approx(one["gross_margin_pct"])
    assert ten["contribution_margin"] == pytest.approx(-150.0)
    with pytest.raises(ValueError):
        z.unit_pnl(100.0, 50.0, units=0)


# --- 2. CAC по каналам -----------------------------------------------------

SPEND = pd.DataFrame({"channel": ["google", "bing", "partner_alpha", "tiktok"],
                      "cost": [5432.12, 3242.73, 10124.05, 1179.34]})
ACQ = pd.DataFrame({"channel": ["google", "bing", "partner_alpha", "email"],
                    "n": [270, 233, 89, 65]})


def test_cac_by_channel():
    t = z.cac_by_channel(SPEND, ACQ)
    assert list(t.columns) == ["channel", "cost", "n", "cac", "note"]
    assert list(t["channel"]) == ["bing", "email", "google", "partner_alpha",
                                  "tiktok"]
    r = t.set_index("channel")
    assert r.loc["google", "cac"] == pytest.approx(20.12, abs=0.01)
    assert r.loc["bing", "cac"] == pytest.approx(13.92, abs=0.01)
    assert r.loc["partner_alpha", "cac"] == pytest.approx(113.75, abs=0.01), \
        "партнёр стоит впятеро дороже поиска за ту же регистрацию"


def test_cac_missing_spend_is_not_zero():
    t = z.cac_by_channel(SPEND, ACQ).set_index("channel")
    assert pd.isna(t.loc["email", "cac"]), \
        ("расход по email неизвестен. Ноль здесь сделал бы канал самым "
         "выгодным, и в него уехал бы бюджет")
    assert t.loc["email", "note"] == "нет данных о расходе"
    assert t.loc["email", "n"] == 65


def test_cac_spend_without_acquisition():
    t = z.cac_by_channel(SPEND, ACQ).set_index("channel")
    assert t.loc["tiktok", "n"] == 0
    assert pd.isna(t.loc["tiktok", "cac"])
    assert t.loc["tiktok", "note"] == "расход без привлечений"
    assert t.loc["tiktok", "cost"] == pytest.approx(1179.34), \
        "1 179 евро потрачено и ноль привлечений — это находка, а не пропуск"


# --- 3. предельный CAC -----------------------------------------------------

def test_breakeven_cac():
    out = z.breakeven_cac(20.0, 0.35, 12)
    assert out["margin_per_period"] == pytest.approx(7.0)
    assert out["breakeven_cac"] == pytest.approx(84.0)
    assert out["undiscounted"] == pytest.approx(84.0)
    with pytest.raises(ValueError):
        z.breakeven_cac(20.0, 0.35, 0)


def test_breakeven_cac_discount_matters():
    plain = z.breakeven_cac(20.0, 0.35, 12)
    disc = z.breakeven_cac(20.0, 0.35, 12, discount=0.02)
    assert disc["breakeven_cac"] == pytest.approx(75.508, abs=1e-3)
    assert disc["undiscounted"] == pytest.approx(84.0)
    assert plain["breakeven_cac"] / disc["breakeven_cac"] > 1.1, \
        "при 2% в месяц дисконт съедает больше десятой части предельного CAC"


# --- 4. окупаемость --------------------------------------------------------

def test_payback_period():
    out = z.payback_period(57.0, [30.0, 25.0, 20.0, 15.0])
    assert out["periods"] == 3
    assert out["exact"] == pytest.approx(2.1), \
        "два периода целиком плюс 2 из 20 третьего"
    assert out["paid_back"] is True
    assert out["cumulative"] == pytest.approx(75.0)


def test_payback_never():
    out = z.payback_period(500.0, [30.0, 25.0, 20.0])
    assert out["paid_back"] is False
    assert out["periods"] is None and out["exact"] is None
    assert out["cumulative"] == pytest.approx(75.0), \
        "накопленное показываем всё равно: видно, насколько не хватило"


# --- 5. LTV на горизонте ---------------------------------------------------

def test_ltv_horizon():
    out = z.ltv_horizon(20.0, [1.0, 0.4, 0.3, 0.25], margin=0.5)
    assert out["horizon"] == 4
    assert out["by_period"] == pytest.approx([10.0, 4.0, 3.0, 2.5])
    assert out["cumulative"] == pytest.approx([10.0, 14.0, 17.0, 19.5])
    assert out["ltv"] == pytest.approx(19.5)


def test_ltv_horizon_vs_infinite_formula():
    """Формула ARPU / отток даёт бесконечный горизонт и завышает."""
    curve = [1.0] + [0.7 ** k for k in range(1, 12)]
    finite = z.ltv_horizon(20.0, curve)["ltv"]
    infinite = 20.0 / 0.3
    assert finite < infinite
    assert finite == pytest.approx(65.744, abs=0.01)
    assert infinite / finite > 1.01, \
        "бесконечный горизонт завышает — и это ещё скромный пример: при отточе 10%% разрыв кратный"


# --- 6-7. когорты ----------------------------------------------------------

CT = pd.DataFrame({"size": [100, 100, 100],
                   "m0": [10.0, 9.0, 8.0],
                   "m1": [12.0, 10.0, 9.0],
                   "m2": [15.0, 11.0, 9.0],
                   "cac": [30.0, 30.0, 30.0]})


def test_cohort_unit_economics():
    t = z.cohort_unit_economics(CT, revenue_cols=["m0", "m1", "m2"])
    assert list(t["cum_m0"]) == pytest.approx([10.0, 9.0, 8.0])
    assert list(t["cum_m2"]) == pytest.approx([37.0, 30.0, 26.0]), \
        "столбцы накапливаются"
    assert list(t["ltv_cac"]) == pytest.approx([1.2333, 1.0, 0.8667], abs=1e-4)
    assert list(t["paid_back"]) == [True, True, False]


def test_convergence_check():
    t = z.cohort_unit_economics(CT, revenue_cols=["m0", "m1", "m2"])
    out = z.convergence_check(t)
    assert out["cohorts"] == 3 and out["converged"] == 2
    assert out["share"] == pytest.approx(2 / 3)
    assert out["worst"] == pytest.approx(0.8667, abs=1e-4)
    assert out["converged_overall"] is False, \
        "сходимость — это когда в плюс выходит каждая когорта, а не средняя"


# --- 8. среднее против когорт ----------------------------------------------

def test_weighted_hides_the_problem():
    co = pd.DataFrame({"size": [700, 100, 100, 100],
                       "ltv": [60.0, 40.0, 38.0, 36.0],
                       "cac": [50.0] * 4})
    out = z.weighted_vs_cohort(co)
    assert out["weighted_ltv"] == pytest.approx(53.4)
    assert out["weighted_ltv_cac"] == pytest.approx(1.068)
    assert out["weighted_profitable"] is True
    assert out["cohorts_profitable"] == 1
    assert out["misleading"] is True, \
        ("средневзвешенно юнит-экономика сходится. Сходится она у одной "
         "когорты из четырёх — остальные три тянет за собой одна большая")


def test_weighted_not_misleading_when_all_profitable():
    co = pd.DataFrame({"size": [100, 100], "ltv": [60.0, 70.0],
                       "cac": [50.0, 50.0]})
    out = z.weighted_vs_cohort(co)
    assert out["misleading"] is False
    assert out["cohorts_profitable"] == 2


# --- 9-10. ожидаемый GGR и его разброс -------------------------------------

def test_expected_ggr():
    bets = pd.DataFrame({"stake": [100.0, 200.0, 50.0],
                         "rtp": [96.0, 94.5, 99.3]})
    out = z.expected_ggr(bets)
    assert out["turnover"] == pytest.approx(350.0)
    assert out["expected_ggr"] == pytest.approx(15.35, abs=1e-6)
    assert out["expected_hold_pct"] == pytest.approx(4.386, abs=1e-3)
    assert out["n_bets"] == 3


def test_expected_ggr_handles_junk():
    bets = pd.DataFrame({"stake": [100.0, None, "нет"], "rtp": [96.0, 96.0, 96.0]})
    out = z.expected_ggr(bets)
    assert out["turnover"] == pytest.approx(100.0)
    assert out["expected_ggr"] == pytest.approx(4.0)


def test_ggr_confidence_small_channel_is_noise():
    out = z.ggr_confidence(7110.71, 3.28, 500)
    assert out["expected_ggr"] == pytest.approx(233.23, abs=0.01)
    assert out["sd"] == pytest.approx(318.0, abs=0.1)
    assert out["lo"] < 0 < out["hi"]
    assert out["reliable"] is False, \
        ("на 500 ставках фактический GGR легко выходит отрицательным при "
         "нормальном проценте удержания. Вывод «канал убыточен» будет "
         "сделан из шума")


def test_ggr_confidence_full_base_is_reliable():
    out = z.ggr_confidence(134448.63, 3.27, 51087)
    assert out["sd_to_expected"] == pytest.approx(0.135, abs=0.01)
    assert out["reliable"] is True
    assert out["lo"] > 0
    assert z.ggr_confidence(100.0, 3.0, 0) is None


# --- 11. реальная стоимость бонусов ----------------------------------------

BONUSES = pd.DataFrame({
    "bonus_id": [1, 2, 3, 4],
    "user_id": [1, 1, 2, 3],
    "amount": [100.0, 50.0, 200.0, 80.0],
    "wager_multiplier": [30, 10, 30, 5],
    "status": ["completed", "completed", "completed", "expired"],
    "granted_ts": ["2026-01-01", "2026-02-01", "2026-01-05", "2026-01-10"],
    "completed_ts": ["2026-01-20", "2026-02-20", "2026-01-25", None],
})
BETS = pd.DataFrame({
    "user_id": [1, 1, 1, 2, 3],
    "ts": ["2026-01-05", "2026-01-10", "2026-02-05", "2026-01-10", "2026-01-15"],
    "stake": [2000.0, 1500.0, 400.0, 900.0, 100.0],
})


def test_bonus_real_cost():
    out = z.bonus_real_cost(BONUSES, BETS)
    assert out["granted"] == pytest.approx(430.0)
    assert out["claimed_completed"] == pytest.approx(350.0)
    assert out["verified_cost"] == pytest.approx(100.0), \
        "отыгран по-настоящему только первый бонус"
    assert out["n_completed"] == 3 and out["n_verified"] == 1
    assert out["overstated_by"] == pytest.approx(250.0)
    assert out["status_reliable"] is False, \
        ("поле статуса ведёт система лояльности, и она врёт. Проверять "
         "надо по ставкам")


def test_bonus_detail():
    d = z.bonus_real_cost(BONUSES, BETS)["detail"]
    assert set(d.columns) >= {"bonus_id", "status", "amount", "required",
                              "staked", "wager_met"}
    r = d.set_index("bonus_id")
    assert r.loc[1, "required"] == pytest.approx(3000.0)
    assert r.loc[1, "staked"] == pytest.approx(3500.0)
    assert bool(r.loc[1, "wager_met"]) is True
    assert r.loc[3, "required"] == pytest.approx(6000.0)
    assert r.loc[3, "staked"] == pytest.approx(900.0)
    assert bool(r.loc[3, "wager_met"]) is False


# --- 12. нормализация канала -----------------------------------------------

def test_normalize_channel():
    out = z.normalize_channel(
        ["Facebook", "facebook ", " Google Ads", "partner-alpha", None, "",
         "FACEBOOK"],
        synonyms={"google_ads": "google"})
    assert out == ["facebook", "facebook", "google", "partner_alpha",
                   "unknown", "unknown", "facebook"]


def test_normalize_channel_merges_split_rows():
    raw = ["facebook"] * 23 + ["Facebook"] * 1
    norm = z.normalize_channel(raw)
    assert len(set(norm)) == 1, \
        ("в базе курса 'Facebook' и 'facebook' — две строки отчёта вместо "
         "одной, и обе выглядят хуже, чем канал на самом деле")
    assert norm.count("facebook") == 24


# --- 13. разложение изменения ----------------------------------------------

def test_metric_gap_decomposition():
    out = z.metric_gap_decomposition(
        {"users": 1000, "cr": 0.05, "check": 100.0},
        {"users": 1100, "cr": 0.04, "check": 110.0})
    assert out["base"] == pytest.approx(5000.0)
    assert out["actual"] == pytest.approx(4840.0)
    assert out["total_change"] == pytest.approx(-160.0)
    c = out["contribution"]
    assert c["users"] == pytest.approx(500.0)
    assert c["cr"] == pytest.approx(-1100.0)
    assert c["check"] == pytest.approx(440.0)
    assert sum(c.values()) == pytest.approx(out["total_change"]), \
        "сумма вкладов обязана точно сходиться с общим изменением"
    assert out["biggest"] == "cr", \
        ("выручка упала на 3%, а конверсия отняла 1 100 из 5 000. "
         "Общая цифра прячет размер проблемы")


def test_metric_gap_decomposition_validates_keys():
    with pytest.raises(ValueError):
        z.metric_gap_decomposition({"a": 1, "b": 2}, {"a": 1, "c": 2})


# --- 14-15. приоритизация --------------------------------------------------

def test_rice_score():
    out = z.rice_score(5000, 0.5, 80, 4)
    assert out["confidence"] == pytest.approx(0.8), "80 — это проценты"
    assert out["score"] == pytest.approx(500.0)
    assert z.rice_score(5000, 0.5, 0.8, 4)["score"] == pytest.approx(500.0)
    with pytest.raises(ValueError):
        z.rice_score(100, 1, 0.5, 0)


def test_ice_geometric_punishes_weak_axis():
    lopsided = z.ice_score(10, 10, 1)
    even = z.ice_score(3, 3, 3)
    assert lopsided["score"] == pytest.approx(4.6416, abs=1e-4)
    assert even["score"] == pytest.approx(3.0)
    assert lopsided["score"] > even["score"]
    unfeasible = z.ice_score(10, 10, 1)
    solid = z.ice_score(5, 5, 5)
    assert solid["score"] > unfeasible["score"], \
        ("ровная идея обгоняет идею, которую невозможно сделать. "
         "При арифметическом среднем было бы наоборот")
    with pytest.raises(ValueError):
        z.ice_score(11, 5, 5)


# --- 16-17. потенциал ------------------------------------------------------

def test_potential_estimate():
    out = z.potential_estimate(15669, 0.28, 0.40, 74.09, capture=0.5)
    assert out["gap"] == pytest.approx(0.12)
    assert out["extra_conversions"] == pytest.approx(940.14)
    assert out["value"] == pytest.approx(69654.97, abs=0.01)
    assert out["worth_doing"] is True


def test_potential_estimate_no_gap():
    out = z.potential_estimate(1000, 0.5, 0.4, 100.0)
    assert out["gap"] == pytest.approx(-0.1)
    assert out["extra_conversions"] == 0.0 and out["value"] == 0.0
    assert out["worth_doing"] is False
    with pytest.raises(ValueError):
        z.potential_estimate(1000, 0.1, 0.5, 10.0, capture=1.4)


def test_segment_opportunity_worst_is_not_biggest():
    seg = pd.DataFrame({"segment": ["ios", "android", "web"],
                        "n": [16073, 17357, 1000],
                        "cr": [0.60, 0.55, 0.30],
                        "value": [100.0, 100.0, 100.0]})
    out = z.segment_opportunity(seg)
    assert out["benchmark"] == pytest.approx(0.60)
    assert out["worst_by_cr"]["segment"] == "web"
    assert out["top_by_potential"]["segment"] == "android"
    assert out["same"] is False, \
        ("хуже всех конвертит веб, но там тысяча человек. Чинить надо "
         "android: разрыв меньше, аудитория в семнадцать раз больше")
    t = out["table"]
    assert list(t["segment"]) == ["android", "web", "ios"]
    assert t.loc[0, "potential"] == pytest.approx(43392.5)
    assert t.loc[2, "potential"] == pytest.approx(0.0)


# --- 18. чувствительность --------------------------------------------------

def _profit(a):
    return a["users"] * a["cr"] * a["value"] - a["cac"] * a["users"]


def test_sensitivity_range():
    out = z.sensitivity_range(
        _profit,
        {"users": 1000, "cr": 0.3, "value": 200.0, "cac": 50.0},
        {"cr": (0.2, 0.4), "value": (150.0, 250.0), "cac": (40.0, 70.0)})
    assert out["base"] == pytest.approx(10000.0)
    t = out["table"]
    assert list(t.columns) == ["assumption", "low", "high", "swing"]
    assert list(t["assumption"])[0] == "cr"
    assert t.loc[0, "swing"] == pytest.approx(40000.0)
    assert out["most_influential"] == "cr"
    assert out["flips_sign"] is True, \
        ("при конверсии 0,2 вместо 0,3 прибыль становится убытком. "
         "Оценка «10 тысяч» без этой оговорки — не аргумент")
