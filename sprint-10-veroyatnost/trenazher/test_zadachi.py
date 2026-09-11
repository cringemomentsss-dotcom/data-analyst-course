"""
Проверка решений тренажёра спринта 10.

Запуск:      make test SPRINT=10
Одна задача: python3 -m pytest sprint-10-veroyatnost/trenazher -q -k bayes
"""

import numpy as np
import pytest
from scipy import stats

import zadachi as z


# --- 1. prob_union ---------------------------------------------------------

def test_prob_union():
    assert z.prob_union(0.3, 0.4) == pytest.approx(0.7), \
        "для несовместных событий вероятности складываются"
    assert z.prob_union(0.3, 0.4, 0.1) == pytest.approx(0.6), \
        "пересечение вычитается, иначе оно посчитано дважды"
    assert z.prob_union(0.5, 0.5, 0.5) == pytest.approx(0.5)


# --- 2. prob_conditional ---------------------------------------------------

def test_prob_conditional():
    assert z.prob_conditional(0.12, 0.3) == pytest.approx(0.4)
    assert z.prob_conditional(0.0, 0.5) == pytest.approx(0.0)
    assert z.prob_conditional(0.1, 0.0) is None, "деление на ноль не должно падать"


# --- 3. bayes --------------------------------------------------------------

def test_bayes():
    # Классика: болезнь у 0,1%, тест ловит 99% больных, ошибается на 1% здоровых.
    # Положительный тест означает болезнь лишь с вероятностью 9%.
    assert z.bayes(0.001, 0.99, 0.01) == pytest.approx(0.0902, abs=0.001)
    assert z.bayes(0.5, 0.9, 0.1) == pytest.approx(0.9)
    assert z.bayes(0.0, 0.99, 0.01) == pytest.approx(0.0)


# --- 4. binom --------------------------------------------------------------

def test_binom_prob_exactly():
    assert z.binom_prob_exactly(10, 3, 0.5) == pytest.approx(stats.binom.pmf(3, 10, 0.5))
    assert z.binom_prob_exactly(1, 1, 0.25) == pytest.approx(0.25)


def test_binom_prob_at_least():
    assert z.binom_prob_at_least(100, 30, 0.266) == pytest.approx(0.2527, abs=0.001)
    assert z.binom_prob_at_least(10, 0, 0.3) == pytest.approx(1.0), \
        "хотя бы ноль успехов — событие достоверное"
    assert z.binom_prob_at_least(10, 11, 0.3) == pytest.approx(0.0)


def test_binom_stats():
    s = z.binom_stats(100, 0.3)
    assert s["mean"] == pytest.approx(30.0)
    assert s["var"] == pytest.approx(21.0)
    assert s["std"] == pytest.approx(np.sqrt(21.0))


# --- 5. poisson ------------------------------------------------------------

def test_poisson():
    assert z.poisson_prob_exactly(10, 10) == pytest.approx(stats.poisson.pmf(10, 10))
    assert z.poisson_prob_at_least(10, 15) == pytest.approx(0.0835, abs=0.001)
    assert z.poisson_prob_at_least(5, 0) == pytest.approx(1.0)


# --- 6. математическое ожидание и дисперсия --------------------------------

def test_expected_value():
    assert z.expected_value([0, 10, 100], [0.7, 0.25, 0.05]) == pytest.approx(7.5)
    assert z.expected_value([1, 1, 1], [0.2, 0.3, 0.5]) == pytest.approx(1.0)


def test_variance_discrete():
    assert z.variance_discrete([0, 10, 100], [0.7, 0.25, 0.05]) == pytest.approx(468.75)
    assert z.variance_discrete([5, 5], [0.5, 0.5]) == pytest.approx(0.0)


# --- 7. нормальное распределение -------------------------------------------

def test_normal_interval_prob():
    assert z.normal_interval_prob(150, 40, 100, 200) == pytest.approx(0.7887, abs=0.001)
    assert z.normal_interval_prob(0, 1, -1, 1) == pytest.approx(0.6827, abs=0.001), \
        "правило одной сигмы"
    assert z.normal_interval_prob(0, 1, -1.96, 1.96) == pytest.approx(0.95, abs=0.001)


def test_normal_quantile():
    assert z.normal_quantile(0, 1, 0.975) == pytest.approx(1.96, abs=0.01)
    assert z.normal_quantile(150, 40, 0.5) == pytest.approx(150.0)


def test_three_sigma_bounds():
    lo, hi = z.three_sigma_bounds(100, 15)
    assert (lo, hi) == pytest.approx((55.0, 145.0))


# --- 8. подгонка распределения ---------------------------------------------

def test_fit_lognormal():
    rng = np.random.default_rng(7)
    sample = rng.lognormal(mean=3.0, sigma=0.8, size=20_000)
    out = z.fit_lognormal(sample)
    assert out["mu"] == pytest.approx(3.0, abs=0.05)
    assert out["sigma"] == pytest.approx(0.8, abs=0.05)
    # нули и None не должны ломать логарифм
    z.fit_lognormal([1.0, 2.0, None, 0.0, 5.0])


# --- 9. проверка нормальности ----------------------------------------------

def test_normality_check():
    rng = np.random.default_rng(11)
    norm = z.normality_check(rng.normal(0, 1, 400))
    assert set(norm) == {"statistic", "pvalue", "looks_normal"}
    assert norm["looks_normal"] is True

    logn = z.normality_check(rng.lognormal(0, 1, 400))
    assert logn["looks_normal"] is False, \
        "логнормальная выборка нормальной быть не должна — именно так распределены деньги"


# --- 10. симуляция ---------------------------------------------------------

def test_simulate_conversion():
    out = z.simulate_conversion(1000, 0.266, 5000, seed=42)
    assert set(out) == {"mean", "std", "p05", "p95"}
    assert out["mean"] == pytest.approx(0.266, abs=0.003), \
        "среднее по симуляции должно сойтись с истинной вероятностью"
    # аналитическая ошибка доли: sqrt(p(1-p)/n)
    assert out["std"] == pytest.approx(np.sqrt(0.266 * 0.734 / 1000), abs=0.002)
    assert out["p05"] < out["mean"] < out["p95"]
    assert z.simulate_conversion(1000, 0.266, 5000, seed=42) == out, \
        "при том же seed результат обязан повторяться"


# --- 11. размер выборки ----------------------------------------------------

def test_sample_size_for_moe():
    assert z.sample_size_for_moe(0.266, 0.02) == 1876
    assert z.sample_size_for_moe(0.5, 0.01) == 9604, \
        "p = 0.5 даёт максимальный требуемый размер"
    assert z.sample_size_for_moe(0.266, 0.01) > z.sample_size_for_moe(0.266, 0.02), \
        "вдвое точнее — вчетверо больше выборка"
