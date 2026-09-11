"""Эталонные решения тренажёра спринта 9. Не подглядывать до решения."""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def describe_numeric(df, cols):
    rows = []
    for c in cols:
        s = pd.to_numeric(df[c], errors="coerce")
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        rows.append({
            "column": c,
            "count": int(s.notna().sum()),
            "missing": int(s.isna().sum()),
            "mean": s.mean(),
            "median": s.median(),
            "std": s.std(),
            "min": s.min(),
            "p25": q1,
            "p75": q3,
            "max": s.max(),
            "iqr": q3 - q1,
        })
    return pd.DataFrame(rows).set_index("column")


def outlier_bounds_iqr(series):
    s = pd.to_numeric(series, errors="coerce")
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


def clip_outliers(series, lower, upper):
    return pd.to_numeric(series, errors="coerce").clip(lower, upper)


def correlation_matrix(df, cols, method="pearson"):
    return df[cols].apply(pd.to_numeric, errors="coerce").corr(method=method).round(3)


def corr_pairs(df, cols, threshold=0.3, method="pearson"):
    m = df[cols].apply(pd.to_numeric, errors="coerce").corr(method=method)
    out = []
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            v = m.loc[a, b]
            if pd.notna(v) and abs(v) >= threshold:
                out.append({"x": a, "y": b, "corr": round(float(v), 3)})
    res = pd.DataFrame(out, columns=["x", "y", "corr"])
    if len(res):
        res = res.reindex(res["corr"].abs().sort_values(ascending=False).index)
    return res.reset_index(drop=True)


def compare_methods(df, x, y):
    a = pd.to_numeric(df[x], errors="coerce")
    b = pd.to_numeric(df[y], errors="coerce")
    return {
        "pearson": round(float(a.corr(b, method="pearson")), 3),
        "spearman": round(float(a.corr(b, method="spearman")), 3),
    }


def histogram_counts(series, bins):
    s = pd.to_numeric(series, errors="coerce").dropna()
    counts, edges = np.histogram(s, bins=bins)
    return counts.tolist(), [round(float(e), 4) for e in edges]


def filter_valid(df, rules):
    """rules: {столбец: (минимум, максимум)}. Возвращает (df, отчёт)."""
    mask = pd.Series(True, index=df.index)
    report = []
    for col, (lo, hi) in rules.items():
        s = pd.to_numeric(df[col], errors="coerce")
        missing = s.isna()
        out_of_range = (~missing) & ((s < lo) | (s > hi))
        report.append({
            "column": col,
            "missing": int(missing.sum()),
            "out_of_range": int(out_of_range.sum()),
        })
        mask &= ~missing & ~out_of_range
    return df[mask].copy(), pd.DataFrame(report).set_index("column")


def group_compare(df, group_col, value_col):
    s = pd.to_numeric(df[value_col], errors="coerce")
    tmp = df.assign(**{value_col: s})
    out = tmp.groupby(group_col, dropna=False)[value_col].agg(
        count="count", mean="mean", median="median", std="std")
    return out.sort_values("median", ascending=False)


def bin_stats(df, value_col, bins, labels, target_col):
    v = pd.to_numeric(df[value_col], errors="coerce")
    t = pd.to_numeric(df[target_col], errors="coerce")
    edges = [-np.inf] + list(bins) + [np.inf]
    bucket = pd.cut(v, bins=edges, labels=labels, right=False)
    tmp = pd.DataFrame({"bucket": bucket, "target": t})
    out = tmp.groupby("bucket", observed=False)["target"].agg(
        count="count", mean="mean", median="median")
    return out


def share_matrix(df, index, columns, values):
    pt = df.pivot_table(index=index, columns=columns, values=values,
                        aggfunc="sum", fill_value=0)
    totals = pt.sum(axis=1).replace(0, np.nan)
    return (100 * pt.div(totals, axis=0)).round(1).fillna(0.0)


def top_bottom(df, key, value, n):
    agg = df.groupby(key, dropna=False)[value].sum().sort_values(ascending=False)
    return agg.head(n), agg.tail(n).sort_values()


def plot_hist(series, ax=None, bins=20):
    s = pd.to_numeric(series, errors="coerce").dropna()
    if ax is None:
        _, ax = plt.subplots()
    ax.hist(s, bins=bins)
    ax.set_xlabel(series.name or "value")
    ax.set_ylabel("Количество")
    return ax


def plot_group_bars(df, group_col, value_col, ax=None):
    agg = group_compare(df, group_col, value_col)["median"].sort_values()
    # в индексе может оказаться NaN — группа с незаполненным ключом.
    # matplotlib примет только строки, поэтому подписываем её явно.
    labels = agg.index.to_series().fillna("не указано").astype(str).tolist()
    if ax is None:
        _, ax = plt.subplots()
    ax.barh(labels, agg.values)
    ax.set_xlabel(value_col)
    ax.set_ylabel(group_col)
    return ax
