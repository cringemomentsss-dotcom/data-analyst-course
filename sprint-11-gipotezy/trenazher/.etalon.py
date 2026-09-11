"""Эталонные решения тренажёра спринта 11. Не подглядывать до решения."""

import numpy as np
from scipy import stats


# --- стандартные ошибки и интервалы ---------------------------------------

def standard_error_mean(sample):
    x = np.asarray([v for v in sample if v is not None], dtype=float)
    return float(x.std(ddof=1) / np.sqrt(len(x)))


def standard_error_prop(p, n):
    return float(np.sqrt(p * (1 - p) / n))


def mean_ci(sample, conf=0.95):
    x = np.asarray([v for v in sample if v is not None], dtype=float)
    n = len(x)
    if n < 2:
        return None
    se = x.std(ddof=1) / np.sqrt(n)
    t = stats.t.ppf(1 - (1 - conf) / 2, df=n - 1)
    m = float(x.mean())
    return {"mean": m, "lo": float(m - t * se), "hi": float(m + t * se),
            "se": float(se), "n": n}


def prop_ci(successes, n, conf=0.95):
    if n == 0:
        return None
    p = successes / n
    z = stats.norm.ppf(1 - (1 - conf) / 2)
    se = np.sqrt(p * (1 - p) / n)
    return {"p": float(p), "lo": float(max(0.0, p - z * se)),
            "hi": float(min(1.0, p + z * se)), "se": float(se), "n": n}


def bootstrap_ci(sample, stat_fn=np.median, n_boot=5000, conf=0.95, seed=42):
    x = np.asarray([v for v in sample if v is not None], dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    stats_boot = np.array([stat_fn(x[i]) for i in idx])
    lo, hi = np.quantile(stats_boot, [(1 - conf) / 2, 1 - (1 - conf) / 2])
    return {"point": float(stat_fn(x)), "lo": float(lo), "hi": float(hi),
            "n_boot": n_boot}


def clt_sampling_distribution(population, n, trials=2000, seed=42):
    """Распределение выборочного среднего: показывает работу ЦПТ."""
    pop = np.asarray(population, dtype=float)
    rng = np.random.default_rng(seed)
    means = np.array([rng.choice(pop, size=n, replace=True).mean()
                      for _ in range(trials)])
    return {
        "mean_of_means": float(means.mean()),
        "std_of_means": float(means.std(ddof=1)),
        "theoretical_se": float(pop.std(ddof=1) / np.sqrt(n)),
        "pop_skew": float(stats.skew(pop)),
        "means_skew": float(stats.skew(means)),
    }


# --- проверка гипотез ------------------------------------------------------

def interpret(pvalue, alpha=0.05):
    reject = bool(pvalue < alpha)
    return {
        "reject_h0": reject,
        "decision": "отвергаем H0" if reject else "не отвергаем H0",
    }


def ttest_one_sample(sample, mu0, alpha=0.05):
    x = np.asarray([v for v in sample if v is not None], dtype=float)
    res = stats.ttest_1samp(x, mu0)
    out = {"statistic": float(res.statistic), "pvalue": float(res.pvalue)}
    out.update(interpret(res.pvalue, alpha))
    return out


def ttest_two_sample(a, b, alpha=0.05, equal_var=False):
    xa = np.asarray([v for v in a if v is not None], dtype=float)
    xb = np.asarray([v for v in b if v is not None], dtype=float)
    res = stats.ttest_ind(xa, xb, equal_var=equal_var)
    diff = float(xb.mean() - xa.mean())
    ci = res.confidence_interval()
    out = {"statistic": float(res.statistic), "pvalue": float(res.pvalue),
           "diff": diff, "ci_lo": float(-ci.high), "ci_hi": float(-ci.low)}
    out.update(interpret(res.pvalue, alpha))
    return out


def mannwhitney(a, b, alpha=0.05):
    xa = np.asarray([v for v in a if v is not None], dtype=float)
    xb = np.asarray([v for v in b if v is not None], dtype=float)
    res = stats.mannwhitneyu(xa, xb, alternative="two-sided")
    out = {"statistic": float(res.statistic), "pvalue": float(res.pvalue)}
    out.update(interpret(res.pvalue, alpha))
    return out


def ztest_proportions(x1, n1, x2, n2, alpha=0.05):
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se_pool = np.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    z = (p2 - p1) / se_pool if se_pool > 0 else 0.0
    pvalue = 2 * stats.norm.sf(abs(z))
    se_diff = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    zc = stats.norm.ppf(1 - alpha / 2)
    out = {"p1": float(p1), "p2": float(p2), "diff": float(p2 - p1),
           "z": float(z), "pvalue": float(pvalue),
           "ci_lo": float(p2 - p1 - zc * se_diff),
           "ci_hi": float(p2 - p1 + zc * se_diff)}
    out.update(interpret(pvalue, alpha))
    return out


def chi2_independence(table, alpha=0.05):
    arr = np.asarray(table, dtype=float)
    chi2, p, dof, _ = stats.chi2_contingency(arr)
    out = {"chi2": float(chi2), "pvalue": float(p), "dof": int(dof)}
    out.update(interpret(p, alpha))
    return out


# --- мощность и размер выборки --------------------------------------------

def mde_proportion(p, n_per_group, alpha=0.05, power=0.8):
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(power)
    return float((z_a + z_b) * np.sqrt(2 * p * (1 - p) / n_per_group))


def sample_size_proportion(p, mde, alpha=0.05, power=0.8):
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(power)
    return int(np.ceil(2 * p * (1 - p) * (z_a + z_b) ** 2 / mde ** 2))


# --- множественная проверка ------------------------------------------------

def bonferroni(pvalues, alpha=0.05):
    m = len(pvalues)
    adj = alpha / m
    return {"alpha_adjusted": float(adj),
            "reject": [bool(p < adj) for p in pvalues],
            "n_reject": int(sum(p < adj for p in pvalues))}


def benjamini_hochberg(pvalues, alpha=0.05):
    p = np.asarray(pvalues, dtype=float)
    m = len(p)
    order = np.argsort(p)
    ranked = p[order]
    thresholds = alpha * (np.arange(1, m + 1) / m)
    passed = ranked <= thresholds
    k = np.where(passed)[0].max() + 1 if passed.any() else 0
    reject = np.zeros(m, dtype=bool)
    if k:
        reject[order[:k]] = True
    return {"n_reject": int(k), "reject": [bool(v) for v in reject]}
