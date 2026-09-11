"""
Проверка решений тренажёра спринта 11.

Запуск:      make test SPRINT=11
Одна задача: python3 -m pytest sprint-11-gipotezy/trenazher -q -k bootstrap
"""

import numpy as np
import pytest
from scipy import stats

import zadachi as z

RNG = np.random.default_rng(0)
NORM_A = RNG.normal(100, 15, 300)
NORM_B = RNG.normal(106, 15, 300)
LOGN = RNG.lognormal(3, 1, 800)


# --- 1. стандартные ошибки -------------------------------------------------

def test_standard_error_mean():
    x = [10.0, 12.0, 14.0, 16.0, 18.0]
    expected = np.std(x, ddof=1) / np.sqrt(5)
    assert z.standard_error_mean(x) == pytest.approx(expected)
    assert z.standard_error_mean([1.0, None, 3.0]) == pytest.approx(
        np.std([1.0, 3.0], ddof=1) / np.sqrt(2)), "None игнорируется"


def test_standard_error_prop():
    assert z.standard_error_prop(0.266, 1200) == pytest.approx(0.012748, abs=1e-5)
    assert z.standard_error_prop(0.5, 100) == pytest.approx(0.05)
    assert z.standard_error_prop(0.266, 4800) == pytest.approx(
        z.standard_error_prop(0.266, 1200) / 2, abs=1e-6), \
        "выборка вчетверо больше — ошибка вдвое меньше"


# --- 2. доверительные интервалы --------------------------------------------

def test_mean_ci():
    out = z.mean_ci(NORM_A, conf=0.95)
    assert set(out) == {"mean", "lo", "hi", "se", "n"}
    assert out["n"] == 300
    assert out["lo"] < out["mean"] < out["hi"]
    assert out["mean"] == pytest.approx(NORM_A.mean())
    # ширина интервала примерно 2 * t * se
    t = stats.t.ppf(0.975, df=299)
    assert (out["hi"] - out["lo"]) == pytest.approx(2 * t * out["se"], rel=1e-6)
    wide = z.mean_ci(NORM_A, conf=0.99)
    assert (wide["hi"] - wide["lo"]) > (out["hi"] - out["lo"]), \
        "99% интервал шире 95%"
    assert z.mean_ci([5.0]) is None


def test_prop_ci():
    out = z.prop_ci(319, 1200)
    assert out["p"] == pytest.approx(0.265833, abs=1e-5)
    assert out["lo"] == pytest.approx(0.24084, abs=0.001)
    assert out["hi"] == pytest.approx(0.29083, abs=0.001)
    assert 0 <= z.prop_ci(1, 10)["lo"], "нижняя граница не может быть отрицательной"
    assert z.prop_ci(10, 10)["hi"] <= 1.0, "верхняя не может быть больше единицы"
    assert z.prop_ci(5, 0) is None


# --- 3. бутстрап -----------------------------------------------------------

def test_bootstrap_ci():
    out = z.bootstrap_ci(LOGN, stat_fn=np.median, n_boot=2000, seed=42)
    assert set(out) >= {"point", "lo", "hi"}
    assert out["point"] == pytest.approx(float(np.median(LOGN)))
    assert out["lo"] < out["point"] < out["hi"]
    same = z.bootstrap_ci(LOGN, stat_fn=np.median, n_boot=2000, seed=42)
    assert same == out, "при том же seed результат обязан повторяться"
    other = z.bootstrap_ci(LOGN, stat_fn=np.mean, n_boot=2000, seed=42)
    assert other["point"] == pytest.approx(float(LOGN.mean())), \
        "функция статистики должна подставляться, а не быть захардкожена"


# --- 4. центральная предельная теорема -------------------------------------

def test_clt_sampling_distribution():
    out = z.clt_sampling_distribution(LOGN, n=200, trials=1500, seed=42)
    assert set(out) >= {"mean_of_means", "std_of_means", "theoretical_se",
                        "pop_skew", "means_skew"}
    assert out["mean_of_means"] == pytest.approx(float(LOGN.mean()), rel=0.05)
    assert out["std_of_means"] == pytest.approx(out["theoretical_se"], rel=0.15), \
        "разброс выборочных средних должен сойтись с теоретической ошибкой"
    assert abs(out["means_skew"]) < abs(out["pop_skew"]) / 3, \
        "средние симметричнее исходной величины — это и есть ЦПТ"
    small = z.clt_sampling_distribution(LOGN, n=5, trials=1500, seed=42)
    assert abs(small["means_skew"]) > abs(out["means_skew"]), \
        "на маленькой выборке ЦПТ ещё не сработала"


# --- 5. интерпретация ------------------------------------------------------

def test_interpret():
    lo = z.interpret(0.001, alpha=0.05)
    hi = z.interpret(0.4, alpha=0.05)
    assert lo["reject_h0"] is True and lo["decision"] == "отвергаем H0"
    assert hi["reject_h0"] is False and hi["decision"] == "не отвергаем H0", \
        "«не отвергаем H0» — не то же, что «H0 верна». Формулировка важна"
    assert z.interpret(0.03, alpha=0.01)["reject_h0"] is False, \
        "решение зависит от заявленного alpha"


# --- 6. t-тесты ------------------------------------------------------------

def test_ttest_one_sample():
    out = z.ttest_one_sample(NORM_A, mu0=100)
    assert set(out) >= {"statistic", "pvalue", "reject_h0", "decision"}
    assert out["reject_h0"] is False, "выборка из N(100,15), гипотеза mu=100 верна"
    far = z.ttest_one_sample(NORM_A, mu0=120)
    assert far["reject_h0"] is True


def test_ttest_two_sample():
    out = z.ttest_two_sample(NORM_A, NORM_B)
    assert set(out) >= {"statistic", "pvalue", "diff", "ci_lo", "ci_hi", "reject_h0"}
    assert out["diff"] == pytest.approx(NORM_B.mean() - NORM_A.mean()), \
        "diff считается как вторая выборка минус первая"
    assert out["ci_lo"] < out["diff"] < out["ci_hi"]
    assert out["reject_h0"] is True, "разница в 6 единиц при sd=15 и n=300 заметна"
    same = z.ttest_two_sample(NORM_A, NORM_A)
    assert same["pvalue"] == pytest.approx(1.0)


def test_ttest_uses_welch_by_default():
    rng = np.random.default_rng(5)
    a = rng.normal(0, 1, 50)
    b = rng.normal(0, 10, 500)      # дисперсии различаются в 100 раз
    welch = z.ttest_two_sample(a, b)
    pooled = z.ttest_two_sample(a, b, equal_var=True)
    assert welch["pvalue"] != pytest.approx(pooled["pvalue"]), \
        "по умолчанию должен быть тест Уэлча, а не с общей дисперсией"


# --- 7. Манна — Уитни ------------------------------------------------------

def test_mannwhitney():
    rng = np.random.default_rng(9)
    a = rng.lognormal(3, 1, 300)
    b = rng.lognormal(3.3, 1, 300)
    out = z.mannwhitney(a, b)
    assert set(out) >= {"statistic", "pvalue", "reject_h0"}
    assert out["reject_h0"] is True
    assert z.mannwhitney(a, a)["reject_h0"] is False


# --- 8. z-тест пропорций ---------------------------------------------------

def test_ztest_proportions():
    out = z.ztest_proportions(319, 1200, 360, 1200)
    assert set(out) >= {"p1", "p2", "diff", "z", "pvalue", "ci_lo", "ci_hi", "reject_h0"}
    assert out["p1"] == pytest.approx(319 / 1200)
    assert out["p2"] == pytest.approx(360 / 1200)
    assert out["diff"] == pytest.approx(360 / 1200 - 319 / 1200)
    assert out["ci_lo"] < out["diff"] < out["ci_hi"]
    assert out["pvalue"] == pytest.approx(0.0632, abs=0.002)
    assert out["reject_h0"] is False, "p-value 0.063 при alpha 0.05 — не отвергаем"
    big = z.ztest_proportions(3190, 12000, 3600, 12000)
    assert big["reject_h0"] is True, \
        "та же разница на выборке в 10 раз больше становится значимой"


# --- 9. хи-квадрат ---------------------------------------------------------

def test_chi2_independence():
    out = z.chi2_independence([[319, 881], [360, 840]])
    assert set(out) >= {"chi2", "pvalue", "dof", "reject_h0"}
    assert out["dof"] == 1
    assert out["pvalue"] == pytest.approx(0.0699, abs=0.002)
    strong = z.chi2_independence([[100, 900], [500, 500]])
    assert strong["reject_h0"] is True


# --- 10. мощность и размер выборки -----------------------------------------

def test_mde_proportion():
    mde = z.mde_proportion(0.266, 19_000)
    assert mde == pytest.approx(0.0127, abs=0.0005)
    assert z.mde_proportion(0.266, 76_000) == pytest.approx(mde / 2, rel=0.02), \
        "выборка вчетверо больше — обнаружимый эффект вдвое меньше"


def test_sample_size_proportion():
    n = z.sample_size_proportion(0.266, 0.01)
    assert n == 30_649
    assert isinstance(n, int)
    assert z.sample_size_proportion(0.266, 0.02) < n
    # согласованность с MDE: посчитанный n должен давать примерно тот же MDE
    assert z.mde_proportion(0.266, n) == pytest.approx(0.01, abs=0.0003)


# --- 11. множественная проверка --------------------------------------------

PVALS = [0.001, 0.02, 0.04, 0.3]


def test_bonferroni():
    out = z.bonferroni(PVALS, alpha=0.05)
    assert out["alpha_adjusted"] == pytest.approx(0.0125)
    assert out["reject"] == [True, False, False, False]
    assert out["n_reject"] == 1


def test_benjamini_hochberg():
    out = z.benjamini_hochberg(PVALS, alpha=0.05)
    assert out["n_reject"] == 2, \
        "процедура Бенджамини — Хохберга мягче Бонферрони"
    assert out["reject"] == [True, True, False, False]
    none = z.benjamini_hochberg([0.4, 0.5, 0.9], alpha=0.05)
    assert none["n_reject"] == 0 and none["reject"] == [False, False, False]
