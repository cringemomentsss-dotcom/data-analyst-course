"""Эталонные решения тренажёра спринта 12. Не подглядывать до решения."""

import numpy as np
import pandas as pd
from scipy import stats


# --- валидация -------------------------------------------------------------

def srm_check(n_control, n_treatment, expected_share=0.5, alpha=0.001):
    n = n_control + n_treatment
    exp_c = n * (1 - expected_share)
    exp_t = n * expected_share
    chi2 = (n_control - exp_c) ** 2 / exp_c + (n_treatment - exp_t) ** 2 / exp_t
    p = float(stats.chi2.sf(chi2, df=1))
    return {
        "n_control": int(n_control), "n_treatment": int(n_treatment),
        "share_treatment": float(n_treatment / n),
        "chi2": float(chi2), "pvalue": p,
        "srm_detected": bool(p < alpha),
    }


def balance_check(share_control, share_treatment, n_control, n_treatment, alpha=0.01):
    """Сбалансированность групп по признаку: доли должны совпадать."""
    x1 = share_control * n_control
    x2 = share_treatment * n_treatment
    p_pool = (x1 + x2) / (n_control + n_treatment)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / n_control + 1 / n_treatment))
    z = (share_treatment - share_control) / se if se > 0 else 0.0
    p = float(2 * stats.norm.sf(abs(z)))
    return {"diff": float(share_treatment - share_control), "z": float(z),
            "pvalue": p, "imbalanced": bool(p < alpha)}


# --- анализ результата -----------------------------------------------------

def ab_proportions(x_control, n_control, x_treatment, n_treatment, alpha=0.05):
    p1, p2 = x_control / n_control, x_treatment / n_treatment
    p_pool = (x_control + x_treatment) / (n_control + n_treatment)
    se_pool = np.sqrt(p_pool * (1 - p_pool) * (1 / n_control + 1 / n_treatment))
    z = (p2 - p1) / se_pool if se_pool > 0 else 0.0
    pvalue = float(2 * stats.norm.sf(abs(z)))
    se_diff = np.sqrt(p1 * (1 - p1) / n_control + p2 * (1 - p2) / n_treatment)
    zc = stats.norm.ppf(1 - alpha / 2)
    return {
        "p_control": float(p1), "p_treatment": float(p2),
        "abs_effect": float(p2 - p1),
        "rel_effect": float(p2 / p1 - 1) if p1 > 0 else None,
        "z": float(z), "pvalue": pvalue,
        "ci_lo": float(p2 - p1 - zc * se_diff),
        "ci_hi": float(p2 - p1 + zc * se_diff),
        "significant": bool(pvalue < alpha),
    }


def ab_means(control, treatment, alpha=0.05):
    a = np.asarray([v for v in control if v is not None], dtype=float)
    b = np.asarray([v for v in treatment if v is not None], dtype=float)
    res = stats.ttest_ind(a, b, equal_var=False)
    ci = res.confidence_interval(confidence_level=1 - alpha)
    return {
        "mean_control": float(a.mean()), "mean_treatment": float(b.mean()),
        "abs_effect": float(b.mean() - a.mean()),
        "rel_effect": float(b.mean() / a.mean() - 1) if a.mean() != 0 else None,
        "pvalue": float(res.pvalue),
        "ci_lo": float(-ci.high), "ci_hi": float(-ci.low),
        "significant": bool(res.pvalue < alpha),
    }


def bootstrap_diff_ci(control, treatment, stat_fn=np.median, n_boot=2000,
                      conf=0.95, seed=42):
    a = np.asarray([v for v in control if v is not None], dtype=float)
    b = np.asarray([v for v in treatment if v is not None], dtype=float)
    rng = np.random.default_rng(seed)
    ia = rng.integers(0, len(a), size=(n_boot, len(a)))
    ib = rng.integers(0, len(b), size=(n_boot, len(b)))
    diffs = np.array([stat_fn(b[j]) - stat_fn(a[i]) for i, j in zip(ia, ib)])
    lo, hi = np.quantile(diffs, [(1 - conf) / 2, 1 - (1 - conf) / 2])
    point = float(stat_fn(b) - stat_fn(a))
    return {"point": point, "ci_lo": float(lo), "ci_hi": float(hi),
            "significant": bool(lo > 0 or hi < 0)}


# --- планирование ----------------------------------------------------------

def mde_proportion(p, n_per_group, alpha=0.05, power=0.8):
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(power)
    return float((z_a + z_b) * np.sqrt(2 * p * (1 - p) / n_per_group))


def sample_size_proportion(p, mde, alpha=0.05, power=0.8):
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(power)
    return int(np.ceil(2 * p * (1 - p) * (z_a + z_b) ** 2 / mde ** 2))


def experiment_duration(daily_units, p, mde, groups=2, alpha=0.05, power=0.8):
    n = sample_size_proportion(p, mde, alpha, power)
    total = n * groups
    days = int(np.ceil(total / daily_units))
    return {"n_per_group": n, "n_total": total,
            "days": days, "weeks": round(days / 7, 1)}


# --- снижение дисперсии ----------------------------------------------------

def cuped_theta(y, y_pre):
    y = np.asarray(y, dtype=float)
    y_pre = np.asarray(y_pre, dtype=float)
    var = y_pre.var(ddof=1)
    if var == 0:
        return 0.0
    return float(np.cov(y, y_pre, ddof=1)[0, 1] / var)


def cuped_adjust(y, y_pre, theta=None):
    y = np.asarray(y, dtype=float)
    y_pre = np.asarray(y_pre, dtype=float)
    if theta is None:
        theta = cuped_theta(y, y_pre)
    return y - theta * (y_pre - y_pre.mean())


def cuped_variance_reduction(y, y_pre):
    y = np.asarray(y, dtype=float)
    adj = cuped_adjust(y, y_pre)
    v0, v1 = y.var(ddof=1), adj.var(ddof=1)
    return {"var_before": float(v0), "var_after": float(v1),
            "reduction_pct": float(100 * (1 - v1 / v0)) if v0 else 0.0,
            "theta": cuped_theta(y, y_pre)}


# --- ловушки ---------------------------------------------------------------

def peeking_false_positive_rate(n_per_group, p, n_peeks, alpha=0.05,
                                trials=2000, seed=42):
    """Симуляция подглядывания: как растёт доля ложных срабатываний."""
    rng = np.random.default_rng(seed)
    checkpoints = np.linspace(n_per_group / n_peeks, n_per_group, n_peeks).astype(int)
    false_positives = 0
    for _ in range(trials):
        a = rng.binomial(1, p, n_per_group)
        b = rng.binomial(1, p, n_per_group)      # эффекта НЕТ
        for k in checkpoints:
            xa, xb = a[:k].sum(), b[:k].sum()
            pp = (xa + xb) / (2 * k)
            se = np.sqrt(pp * (1 - pp) * 2 / k) if 0 < pp < 1 else 0
            if se > 0 and abs((xb / k - xa / k) / se) > stats.norm.ppf(1 - alpha / 2):
                false_positives += 1
                break
    return {"n_peeks": n_peeks, "nominal_alpha": alpha,
            "actual_fpr": float(false_positives / trials)}


def segment_analysis(df, segment_col, variant_col, success_col, alpha=0.05):
    """z-тест по каждому сегменту с поправкой Бонферрони."""
    rows = []
    for seg, g in df.groupby(segment_col, dropna=False):
        c = g[g[variant_col] == "control"]
        t = g[g[variant_col] == "treatment"]
        if len(c) == 0 or len(t) == 0:
            continue
        r = ab_proportions(c[success_col].sum(), len(c),
                           t[success_col].sum(), len(t), alpha)
        rows.append({"segment": seg, "n_control": len(c), "n_treatment": len(t),
                     "p_control": r["p_control"], "p_treatment": r["p_treatment"],
                     "abs_effect": r["abs_effect"], "pvalue": r["pvalue"]})
    out = pd.DataFrame(rows)
    if len(out):
        adj = alpha / len(out)
        out["significant_raw"] = out["pvalue"] < alpha
        out["significant_adjusted"] = out["pvalue"] < adj
        out.attrs["alpha_adjusted"] = adj
    return out


def simpson_check(overall_effect, segment_effects):
    """Есть ли смена знака между общим эффектом и эффектами по сегментам."""
    signs = [np.sign(e) for e in segment_effects if e is not None and e != 0]
    overall_sign = np.sign(overall_effect)
    flipped = bool(signs) and all(s != overall_sign for s in signs)
    return {"overall_sign": int(overall_sign),
            "segment_signs": [int(s) for s in signs],
            "paradox_detected": flipped}
