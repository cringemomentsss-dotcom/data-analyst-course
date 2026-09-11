"""Эталонные решения тренажёра спринта 10. Не подглядывать до решения."""

import numpy as np
from scipy import stats


# --- вероятности -----------------------------------------------------------

def prob_union(p_a, p_b, p_both=0.0):
    return p_a + p_b - p_both


def prob_conditional(p_both, p_condition):
    if p_condition == 0:
        return None
    return p_both / p_condition


def bayes(prior, tpr, fpr):
    """P(болен | тест положителен) при заданных prior, чувствительности и FPR."""
    num = prior * tpr
    den = num + (1 - prior) * fpr
    if den == 0:
        return None
    return num / den


# --- дискретные распределения ---------------------------------------------

def binom_prob_exactly(n, k, p):
    return float(stats.binom.pmf(k, n, p))


def binom_prob_at_least(n, k, p):
    return float(stats.binom.sf(k - 1, n, p))


def binom_stats(n, p):
    return {"mean": n * p, "var": n * p * (1 - p), "std": float(np.sqrt(n * p * (1 - p)))}


def poisson_prob_exactly(lam, k):
    return float(stats.poisson.pmf(k, lam))


def poisson_prob_at_least(lam, k):
    return float(stats.poisson.sf(k - 1, lam))


def expected_value(values, probs):
    v = np.asarray(values, dtype=float)
    p = np.asarray(probs, dtype=float)
    return float((v * p).sum())


def variance_discrete(values, probs):
    v = np.asarray(values, dtype=float)
    p = np.asarray(probs, dtype=float)
    mu = (v * p).sum()
    return float((((v - mu) ** 2) * p).sum())


# --- непрерывные распределения --------------------------------------------

def normal_interval_prob(mu, sigma, lo, hi):
    return float(stats.norm.cdf(hi, mu, sigma) - stats.norm.cdf(lo, mu, sigma))


def normal_quantile(mu, sigma, q):
    return float(stats.norm.ppf(q, mu, sigma))


def three_sigma_bounds(mu, sigma):
    return mu - 3 * sigma, mu + 3 * sigma


def fit_lognormal(sample):
    """Оценить параметры логнормального распределения по выборке."""
    x = np.asarray([v for v in sample if v is not None and v > 0], dtype=float)
    logs = np.log(x)
    return {"mu": float(logs.mean()), "sigma": float(logs.std(ddof=1))}


def normality_check(sample):
    """Проверка нормальности критерием Шапиро — Уилка."""
    x = np.asarray([v for v in sample if v is not None], dtype=float)
    st, p = stats.shapiro(x)
    return {"statistic": round(float(st), 4), "pvalue": round(float(p), 6),
            "looks_normal": bool(p > 0.05)}


# --- симуляция -------------------------------------------------------------

def simulate_conversion(n, p, trials, seed=42):
    """Монте-Карло: доля конверсии в trials повторениях по n наблюдений."""
    rng = np.random.default_rng(seed)
    draws = rng.binomial(n, p, size=trials) / n
    return {
        "mean": float(draws.mean()),
        "std": float(draws.std(ddof=1)),
        "p05": float(np.quantile(draws, 0.05)),
        "p95": float(np.quantile(draws, 0.95)),
    }


def sample_size_for_moe(p, moe, conf=0.95):
    """Размер выборки для оценки доли с заданной точностью."""
    z = stats.norm.ppf(1 - (1 - conf) / 2)
    return int(np.ceil(z ** 2 * p * (1 - p) / moe ** 2))
