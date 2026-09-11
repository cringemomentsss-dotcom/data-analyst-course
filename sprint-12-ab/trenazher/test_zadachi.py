"""
Проверка решений тренажёра спринта 12.

Запуск:      make test SPRINT=12
Одна задача: python3 -m pytest sprint-12-ab/trenazher -q -k srm
"""

import numpy as np
import pandas as pd
import pytest

import zadachi as z


# --- 1. SRM ----------------------------------------------------------------

def test_srm_check_ok():
    out = z.srm_check(21746, 21713)
    assert set(out) >= {"n_control", "n_treatment", "share_treatment",
                        "chi2", "pvalue", "srm_detected"}
    assert out["share_treatment"] == pytest.approx(0.49962, abs=1e-4)
    assert out["pvalue"] > 0.5
    assert out["srm_detected"] is False


def test_srm_check_broken():
    out = z.srm_check(23455, 24418)
    assert out["chi2"] == pytest.approx(19.371, abs=0.01)
    assert out["pvalue"] == pytest.approx(1.08e-05, rel=0.1)
    assert out["srm_detected"] is True, \
        "перекос 51/49 на выборке 48 тысяч — это сломанное бакетирование"


def test_srm_small_sample_low_power():
    out = z.srm_check(92, 70)
    assert out["srm_detected"] is False, \
        "перекос 57/43 выглядит хуже, но на 162 наблюдениях тест его не поймает"
    assert out["pvalue"] > 0.001


def test_srm_uneven_expected_share():
    out = z.srm_check(900, 100, expected_share=0.1)
    assert out["srm_detected"] is False, \
        "план 90/10 надо уметь проверять, а не только 50/50"


# --- 2. балансировка -------------------------------------------------------

def test_balance_check():
    ok = z.balance_check(0.2852, 0.2802, 21746, 21713)
    assert ok["imbalanced"] is False
    bad = z.balance_check(0.1708, 0.3822, 23455, 24418)
    assert bad["imbalanced"] is True, \
        "доля десктопа 17% против 38% — группы несравнимы"
    assert bad["diff"] == pytest.approx(0.2114, abs=0.001)


# --- 3. анализ пропорций ---------------------------------------------------

def test_ab_proportions_win():
    out = z.ab_proportions(761, 21746, 963, 21713)
    assert out["p_control"] == pytest.approx(0.03499, abs=1e-4)
    assert out["p_treatment"] == pytest.approx(0.04435, abs=1e-4)
    assert out["abs_effect"] == pytest.approx(0.00936, abs=1e-4)
    assert out["rel_effect"] == pytest.approx(0.2674, abs=0.001)
    assert out["ci_lo"] == pytest.approx(0.00569, abs=1e-4)
    assert out["ci_hi"] == pytest.approx(0.01303, abs=1e-4)
    assert out["significant"] is True
    assert out["ci_lo"] > 0, "интервал не содержит нуля — значит эффект есть"


def test_ab_proportions_null():
    out = z.ab_proportions(71, 92, 49, 70)
    assert out["pvalue"] == pytest.approx(0.302, abs=0.005)
    assert out["significant"] is False
    assert out["ci_lo"] < 0 < out["ci_hi"], \
        "интервал накрывает ноль — эффект не обнаружен"
    assert (out["ci_hi"] - out["ci_lo"]) > 0.2, \
        "интервал шириной больше 20 п.п. означает, что тест ничего не измерил"


def test_ab_proportions_symmetry():
    a = z.ab_proportions(100, 1000, 120, 1000)
    b = z.ab_proportions(120, 1000, 100, 1000)
    assert a["abs_effect"] == pytest.approx(-b["abs_effect"])
    assert a["pvalue"] == pytest.approx(b["pvalue"])


# --- 4. анализ средних -----------------------------------------------------

def test_ab_means():
    rng = np.random.default_rng(4)
    a = rng.normal(100, 20, 500)
    b = rng.normal(106, 20, 500)
    out = z.ab_means(a, b)
    assert out["abs_effect"] == pytest.approx(b.mean() - a.mean())
    assert out["ci_lo"] < out["abs_effect"] < out["ci_hi"]
    assert out["significant"] is True
    same = z.ab_means(a, a)
    assert same["significant"] is False
    assert same["abs_effect"] == pytest.approx(0.0)


# --- 5. бутстрап разницы ---------------------------------------------------

def test_bootstrap_diff_ci():
    rng = np.random.default_rng(6)
    a = rng.lognormal(3, 1, 400)
    b = rng.lognormal(3.4, 1, 400)
    out = z.bootstrap_diff_ci(a, b, stat_fn=np.median, n_boot=800, seed=42)
    assert out["point"] == pytest.approx(float(np.median(b) - np.median(a)))
    assert out["ci_lo"] < out["point"] < out["ci_hi"]
    assert out["significant"] is True
    again = z.bootstrap_diff_ci(a, b, stat_fn=np.median, n_boot=800, seed=42)
    assert again == out, "seed должен давать воспроизводимость"
    null = z.bootstrap_diff_ci(a, a, stat_fn=np.median, n_boot=800, seed=42)
    assert null["significant"] is False


# --- 6. планирование -------------------------------------------------------

def test_mde_and_sample_size():
    assert z.mde_proportion(0.035, 21746) == pytest.approx(0.00493, abs=0.0002)
    n = z.sample_size_proportion(0.035, 0.005)
    assert isinstance(n, int)
    assert z.mde_proportion(0.035, n) == pytest.approx(0.005, abs=0.0002), \
        "MDE и размер выборки должны быть согласованы"


def test_experiment_duration():
    out = z.experiment_duration(1400, 0.035, 0.005)
    assert set(out) >= {"n_per_group", "n_total", "days", "weeks"}
    assert out["n_total"] == out["n_per_group"] * 2
    assert out["days"] == 31
    faster = z.experiment_duration(2800, 0.035, 0.005)
    assert faster["days"] < out["days"], "вдвое больше трафика — вдвое короче тест"


# --- 7. CUPED --------------------------------------------------------------

def test_cuped_variance_reduction():
    rng = np.random.default_rng(3)
    pre = rng.lognormal(3, 0.7, 4000)
    y = pre * 0.8 + rng.lognormal(3, 0.5, 4000)
    out = z.cuped_variance_reduction(y, pre)
    assert out["reduction_pct"] > 40, \
        "при сильной связи с предпериодом дисперсия должна упасть заметно"
    assert out["var_after"] < out["var_before"]
    assert out["theta"] == pytest.approx(0.798, abs=0.01)


def test_cuped_no_covariate():
    rng = np.random.default_rng(8)
    y = rng.normal(10, 3, 2000)
    noise = rng.normal(5, 3, 2000)      # предпериод не связан с метрикой
    out = z.cuped_variance_reduction(y, noise)
    assert abs(out["reduction_pct"]) < 5, \
        "без связи с предпериодом CUPED ничего не даёт — и не должен вредить"


def test_cuped_adjust_preserves_mean():
    rng = np.random.default_rng(9)
    pre = rng.normal(10, 2, 1000)
    y = pre + rng.normal(0, 1, 1000)
    adj = z.cuped_adjust(y, pre)
    assert adj.mean() == pytest.approx(y.mean(), abs=1e-9), \
        "CUPED снижает дисперсию, но не сдвигает среднее"


# --- 8. подглядывание ------------------------------------------------------

def test_peeking_inflates_false_positives():
    one = z.peeking_false_positive_rate(2000, 0.05, n_peeks=1,
                                        trials=400, seed=1)
    many = z.peeking_false_positive_rate(2000, 0.05, n_peeks=10,
                                         trials=400, seed=1)
    assert one["actual_fpr"] == pytest.approx(0.05, abs=0.04), \
        "без подглядывания доля ложных срабатываний близка к номинальному alpha"
    assert many["actual_fpr"] > 2 * one["actual_fpr"], \
        "десять подглядываний должны кратно поднять долю ложных срабатываний"


# --- 9. сегменты -----------------------------------------------------------

def make_segment_df():
    rng = np.random.default_rng(12)
    rows = []
    for seg, p_c, p_t, n in [("mobile", 0.03, 0.037, 6000),
                             ("desktop", 0.05, 0.061, 3000),
                             ("tablet", 0.04, 0.040, 800)]:
        for variant, p in [("control", p_c), ("treatment", p_t)]:
            for s in rng.binomial(1, p, n):
                rows.append({"segment": seg, "variant": variant, "success": s})
    return pd.DataFrame(rows)


def test_segment_analysis():
    df = make_segment_df()
    out = z.segment_analysis(df, "segment", "variant", "success")
    assert set(out.columns) >= {"segment", "n_control", "n_treatment",
                                "p_control", "p_treatment", "abs_effect",
                                "pvalue", "significant_raw", "significant_adjusted"}
    assert len(out) == 3
    assert (out["significant_adjusted"] <= out["significant_raw"]).all(), \
        "с поправкой значимых не может стать больше"
    tablet = out[out.segment == "tablet"].iloc[0]
    assert tablet["significant_raw"] is np.False_ or not tablet["significant_raw"]


# --- 10. Симпсонов парадокс ------------------------------------------------

def test_simpson_check():
    flipped = z.simpson_check(0.02, [-0.01, -0.015, -0.005])
    assert flipped["paradox_detected"] is True, \
        "общий эффект положительный, во всех сегментах отрицательный — парадокс"
    normal = z.simpson_check(0.02, [0.01, 0.03, 0.015])
    assert normal["paradox_detected"] is False
    mixed = z.simpson_check(0.02, [0.01, -0.03])
    assert mixed["paradox_detected"] is False, \
        "парадокс — это когда ВСЕ сегменты против общего, а не когда они разные"
