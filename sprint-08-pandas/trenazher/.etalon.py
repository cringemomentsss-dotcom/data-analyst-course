"""Эталонные решения тренажёра спринта 8. Не подглядывать до решения."""

import numpy as np
import pandas as pd

MISSING_MARKERS = ["", " ", "NaN", "nan", "null", "NULL", "-", "н/д", "н\\д", "none"]


def load_csv(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def to_missing(series):
    return series.astype("object").where(~series.astype(str).str.strip().isin(MISSING_MARKERS), np.nan)


def to_number(series):
    s = to_missing(series).astype("object")
    s = s.apply(lambda x: x if pd.isna(x) else str(x))
    s = s.str.replace(r"[^\d,.\-]", "", regex=True)
    s = s.str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def parse_dates(series):
    """Разобрать даты двух форматов.

    Ловушка: dayfirst=True применяется и к ISO-строкам, поэтому
    '2026-03-01' превращается в 3 января. Поэтому форматы разбираем
    отдельно: ISO — как есть, остальное — с dayfirst.
    """
    txt = to_missing(series).astype("object")
    txt = txt.apply(lambda x: x if pd.isna(x) else str(x).strip())
    as_str = txt.astype(str)
    is_iso = as_str.str.match(r"^\d{4}-\d{2}-\d{2}") & txt.notna()
    is_dmy = txt.notna() & ~is_iso

    out = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    if is_iso.any():
        out[is_iso] = pd.to_datetime(txt[is_iso], format="ISO8601", errors="coerce")
    if is_dmy.any():
        out[is_dmy] = pd.to_datetime(txt[is_dmy], dayfirst=True,
                                     format="mixed", errors="coerce")
    return out


def normalize_categorical(series, mapping=None):
    s = to_missing(series)
    s = s.astype("object").apply(lambda x: x if pd.isna(x) else str(x).strip().lower())
    if mapping:
        low = {str(k).strip().lower(): v for k, v in mapping.items()}
        s = s.replace(low)
    return s


def missing_report(df):
    total = len(df)
    rows = []
    for col in df.columns:
        n = int(df[col].isna().sum())
        rows.append({
            "column": col,
            "missing": n,
            "missing_pct": round(100 * n / total, 1) if total else 0.0,
        })
    return pd.DataFrame(rows).sort_values(
        ["missing", "column"], ascending=[False, True]).reset_index(drop=True)


def drop_dupes(df, subset):
    before = len(df)
    out = df.drop_duplicates(subset=subset, keep="first").reset_index(drop=True)
    return out, before - len(out)


def add_bucket(df, col, bounds, labels):
    edges = [-np.inf] + list(bounds) + [np.inf]
    out = df.copy()
    out["bucket"] = pd.cut(out[col], bins=edges, labels=labels, right=False)
    return out


def revenue_by(df, key, value):
    return df.groupby(key, dropna=False)[value].sum().sort_values(ascending=False)


def agg_multi(df, key, value):
    out = df.groupby(key, dropna=False)[value].agg(
        count="count", total="sum", mean="mean", median="median")
    return out.sort_values("total", ascending=False)


def top_n_by(df, key, value, n):
    return df.groupby(key, dropna=False)[value].sum().sort_values(
        ascending=False).head(n)


def pivot_summary(df, index, columns, values):
    return df.pivot_table(index=index, columns=columns, values=values,
                          aggfunc="sum", fill_value=0)


def join_ltv(players, purchases):
    ltv = purchases.groupby("player_id")["price"].sum().rename("ltv")
    out = players.merge(ltv, left_on="player_id", right_index=True,
                        how="left", validate="one_to_one")
    out["ltv"] = out["ltv"].fillna(0.0)
    out["is_payer"] = out["ltv"] > 0
    return out


def monthly_series(df, ts_col, value_col):
    s = df.set_index(ts_col)[value_col].resample("MS").sum()
    full = pd.date_range(s.index.min(), s.index.max(), freq="MS")
    return s.reindex(full, fill_value=0.0)


def share_of_total(series):
    total = series.sum()
    if total == 0:
        return series * 0.0
    return (100 * series / total).round(1)


def iqr_bounds(series):
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


def detect_outliers_iqr(series):
    lo, hi = iqr_bounds(series)
    return (series < lo) | (series > hi)
