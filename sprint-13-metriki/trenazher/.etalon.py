"""Эталонные решения тренажёра спринта 13. Не подглядывать до решения."""

import numpy as np
import pandas as pd


# --- активность ------------------------------------------------------------

def dau_wau_mau(sessions, user_col="user_id", ts_col="ts"):
    s = sessions.copy()
    s[ts_col] = pd.to_datetime(s[ts_col])
    day = s.groupby(s[ts_col].dt.date)[user_col].nunique()
    week = s.groupby(s[ts_col].dt.to_period("W"))[user_col].nunique()
    month = s.groupby(s[ts_col].dt.to_period("M"))[user_col].nunique()
    dau, wau, mau = float(day.mean()), float(week.mean()), float(month.mean())
    return {"dau": dau, "wau": wau, "mau": mau,
            "sticky_dau_mau": float(dau / mau) if mau else None,
            "sticky_dau_wau": float(dau / wau) if wau else None}


def active_users(events, day, window=1, user_col="user_id", ts_col="ts",
                 name_col=None, active_events=None):
    """Активные за окно, заканчивающееся днём day включительно."""
    e = events[[c for c in events.columns]].copy()
    e[ts_col] = pd.to_datetime(e[ts_col])
    if active_events is not None:
        if name_col is None:
            raise ValueError("active_events задан, а name_col нет")
        e = e[e[name_col].isin(active_events)]
    end = pd.Timestamp(day).normalize()
    start = end - pd.Timedelta(days=window - 1)
    mask = (e[ts_col].dt.normalize() >= start) & (e[ts_col].dt.normalize() <= end)
    sel = e.loc[mask]
    return {"day": end.date(), "window": int(window),
            "users": int(sel[user_col].nunique()),
            "events": int(len(sel))}


# --- retention -------------------------------------------------------------

def _prep(users, events, user_col, reg_col, ts_col):
    u = users[[user_col, reg_col]].copy()
    u[reg_col] = pd.to_datetime(u[reg_col]).dt.normalize()
    e = events[[user_col, ts_col]].copy()
    e[ts_col] = pd.to_datetime(e[ts_col]).dt.normalize()
    m = e.merge(u, on=user_col, how="inner")
    m["day_n"] = (m[ts_col] - m[reg_col]).dt.days
    return u, m


def retention_nday(users, events, n, user_col="user_id",
                   reg_col="reg_date", ts_col="ts"):
    """N-day retention: активность РОВНО на день N."""
    u, m = _prep(users, events, user_col, reg_col, ts_col)
    retained = m.loc[m["day_n"] == n, user_col].nunique()
    total = u[user_col].nunique()
    return {"n": n, "cohort_size": int(total), "retained": int(retained),
            "retention": float(retained / total) if total else None}


def rolling_retention(users, events, n, user_col="user_id",
                      reg_col="reg_date", ts_col="ts"):
    """Rolling retention: активность на день N ИЛИ ПОЗЖЕ."""
    u, m = _prep(users, events, user_col, reg_col, ts_col)
    retained = m.loc[m["day_n"] >= n, user_col].nunique()
    total = u[user_col].nunique()
    return {"n": n, "cohort_size": int(total), "retained": int(retained),
            "retention": float(retained / total) if total else None}


def unbounded_retention(users, events, n, user_col="user_id",
                        reg_col="reg_date", ts_col="ts"):
    """Unbounded (bracket) retention: активность в интервале [1, N]."""
    u, m = _prep(users, events, user_col, reg_col, ts_col)
    retained = m.loc[(m["day_n"] >= 1) & (m["day_n"] <= n), user_col].nunique()
    total = u[user_col].nunique()
    return {"n": n, "cohort_size": int(total), "retained": int(retained),
            "retention": float(retained / total) if total else None}


def retention_curve(users, events, max_day=14, user_col="user_id",
                    reg_col="reg_date", ts_col="ts"):
    u, m = _prep(users, events, user_col, reg_col, ts_col)
    total = u[user_col].nunique()
    rows = []
    for d in range(0, max_day + 1):
        r = m.loc[m["day_n"] == d, user_col].nunique()
        rows.append({"day_n": d, "retained": int(r),
                     "retention": float(r / total) if total else None})
    return pd.DataFrame(rows)


def cohort_matrix(users, events, max_period=6, freq="M", user_col="user_id",
                  reg_col="reg_date", ts_col="ts"):
    """Retention-матрица: когорты по периоду регистрации × номер периода."""
    u = users[[user_col, reg_col]].copy()
    u[reg_col] = pd.to_datetime(u[reg_col])
    u["cohort"] = u[reg_col].dt.to_period(freq)
    e = events[[user_col, ts_col]].copy()
    e[ts_col] = pd.to_datetime(e[ts_col])
    e["period"] = e[ts_col].dt.to_period(freq)
    m = e.merge(u[[user_col, "cohort"]], on=user_col, how="inner")
    m["period_n"] = (m["period"] - m["cohort"]).apply(lambda x: x.n)
    m = m[(m["period_n"] >= 0) & (m["period_n"] <= max_period)]
    counts = m.groupby(["cohort", "period_n"])[user_col].nunique().unstack(fill_value=0)
    sizes = u.groupby("cohort")[user_col].nunique()
    counts = counts.reindex(index=sizes.index,
                            columns=range(0, max_period + 1), fill_value=0)
    counts = counts.fillna(0)
    return (100 * counts.div(sizes, axis=0)).round(1)


# --- воронки ---------------------------------------------------------------

def funnel_open(events, steps, user_col="user_id", name_col="event_name"):
    """Открытая воронка: уникальные пользователи на каждом шаге, без порядка."""
    rows = []
    prev = None
    for s in steps:
        u = events.loc[events[name_col] == s, user_col].nunique()
        rows.append({"step": s, "users": int(u),
                     "step_cr": None if prev in (None, 0) else round(100 * u / prev, 2),
                     "from_top": None})
        prev = u
    top = rows[0]["users"]
    for r in rows:
        r["from_top"] = round(100 * r["users"] / top, 2) if top else None
    return pd.DataFrame(rows)


def funnel_closed(events, steps, user_col="user_id", name_col="event_name",
                  ts_col="ts"):
    """Закрытая воронка: шаг засчитывается только если предыдущие были РАНЬШЕ."""
    e = events[[user_col, name_col, ts_col]].copy()
    e[ts_col] = pd.to_datetime(e[ts_col])
    first = e.groupby([user_col, name_col])[ts_col].min().unstack()
    alive = pd.Series(True, index=first.index)
    prev_ts = None
    rows = []
    prev_n = None
    for s in steps:
        if s in first.columns:
            col = first[s]
        else:
            col = pd.Series(pd.NaT, index=first.index, dtype=e[ts_col].dtype)
        has = col.notna()
        if prev_ts is None:
            alive = alive & has
        else:
            alive = alive & has & (col >= prev_ts)
        n = int(alive.sum())
        rows.append({"step": s, "users": n,
                     "step_cr": None if prev_n in (None, 0) else round(100 * n / prev_n, 2)})
        prev_ts = col.where(alive)
        prev_n = n
    top = rows[0]["users"]
    for r in rows:
        r["from_top"] = round(100 * r["users"] / top, 2) if top else None
    return pd.DataFrame(rows)


def funnel_by_segment(events, steps, segment_col, user_col="user_id",
                      name_col="event_name", ts_col="ts"):
    """Закрытая воронка в разрезе сегмента. Возвращает длинный DataFrame."""
    out = []
    for seg in sorted(events[segment_col].dropna().unique()):
        part = events[events[segment_col] == seg]
        f = funnel_closed(part, steps, user_col=user_col,
                          name_col=name_col, ts_col=ts_col)
        f.insert(0, "segment", seg)
        out.append(f)
    if not out:
        return pd.DataFrame(columns=["segment", "step", "users", "step_cr", "from_top"])
    return pd.concat(out, ignore_index=True)


def time_to_convert(events, step_from, step_to, user_col="user_id",
                    name_col="event_name", ts_col="ts"):
    e = events[[user_col, name_col, ts_col]].copy()
    e[ts_col] = pd.to_datetime(e[ts_col])
    a = e[e[name_col] == step_from].groupby(user_col)[ts_col].min()
    b = e[e[name_col] == step_to].groupby(user_col)[ts_col].min()
    both = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    both = both[both["b"] >= both["a"]]
    hours = (both["b"] - both["a"]).dt.total_seconds() / 3600
    if len(hours) == 0:
        return None
    return {"n": int(len(hours)), "median_hours": float(hours.median()),
            "mean_hours": float(hours.mean()),
            "p90_hours": float(hours.quantile(0.9))}


# --- деньги ----------------------------------------------------------------

def arpu_arppu(n_users, orders, revenue_col="revenue", user_col="user_id"):
    rev = float(orders[revenue_col].sum())
    payers = int(orders[user_col].nunique())
    return {"revenue": rev, "users": int(n_users), "payers": payers,
            "arpu": rev / n_users if n_users else None,
            "arppu": rev / payers if payers else None,
            "payer_share": payers / n_users if n_users else None,
            "avg_order": rev / len(orders) if len(orders) else None}


def avg_check(orders, revenue_col="revenue"):
    """Средний чек: среднее, медиана и оценка перекоса хвостом."""
    x = pd.to_numeric(orders[revenue_col], errors="coerce").dropna()
    if len(x) == 0:
        return None
    mean, median = float(x.mean()), float(x.median())
    top = x.sort_values(ascending=False)
    n_top = max(1, int(round(0.01 * len(x))))
    return {"n": int(len(x)), "mean": mean, "median": median,
            "p90": float(x.quantile(0.9)),
            "skew_ratio": mean / median if median else None,
            "top1pct_revenue_share": float(top.head(n_top).sum() / x.sum())
            if x.sum() else None}


def ggr_ngr(bets, bet_col="bet", win_col="win", bonus_col=None, fees=0.0):
    """GGR = ставки − выплаты. NGR = GGR − бонусы − комиссии."""
    b = float(pd.to_numeric(bets[bet_col], errors="coerce").fillna(0).sum())
    w = float(pd.to_numeric(bets[win_col], errors="coerce").fillna(0).sum())
    ggr = b - w
    bonus = 0.0
    if bonus_col is not None and bonus_col in bets.columns:
        bonus = float(pd.to_numeric(bets[bonus_col], errors="coerce").fillna(0).sum())
    ngr = ggr - bonus - float(fees)
    return {"turnover": b, "payout": w, "ggr": ggr, "bonus": bonus,
            "fees": float(fees), "ngr": ngr,
            "hold_pct": 100 * ggr / b if b else None,
            "rtp_pct": 100 * w / b if b else None}


def ltv_by_cohort(users, orders, max_period=6, freq="M", user_col="user_id",
                  reg_col="reg_date", ts_col="ts", revenue_col="revenue"):
    """Накопленный LTV по когортам: сколько денег принёс пользователь к периоду N."""
    u = users[[user_col, reg_col]].copy()
    u[reg_col] = pd.to_datetime(u[reg_col])
    u["cohort"] = u[reg_col].dt.to_period(freq)
    o = orders[[user_col, ts_col, revenue_col]].copy()
    o[ts_col] = pd.to_datetime(o[ts_col])
    o["period"] = o[ts_col].dt.to_period(freq)
    m = o.merge(u[[user_col, "cohort"]], on=user_col, how="inner")
    m["period_n"] = (m["period"] - m["cohort"]).apply(lambda x: x.n)
    m = m[(m["period_n"] >= 0) & (m["period_n"] <= max_period)]
    sizes = u.groupby("cohort")[user_col].nunique()
    if len(m) == 0:
        rev = pd.DataFrame(0.0, index=sizes.index,
                           columns=range(0, max_period + 1))
    else:
        rev = m.groupby(["cohort", "period_n"])[revenue_col].sum().unstack()
        rev = rev.reindex(index=sizes.index,
                          columns=range(0, max_period + 1)).fillna(0.0)
    return (rev.cumsum(axis=1).div(sizes, axis=0)).round(2)


def unit_economics(cac, arpu, margin=1.0):
    """LTV/CAC и срок окупаемости в периодах ARPU."""
    ltv = arpu * margin
    if cac == 0:
        return {"ltv": ltv, "cac": 0.0, "ltv_cac": None, "payback_periods": None,
                "profitable": True}
    return {"ltv": float(ltv), "cac": float(cac),
            "ltv_cac": float(ltv / cac),
            "payback_periods": float(cac / ltv) if ltv > 0 else None,
            "profitable": bool(ltv > cac)}


# --- контроль --------------------------------------------------------------

def sanity_check(parts, total, tol=0.01):
    """Сумма по разрезам должна сходиться с общим итогом."""
    s = float(np.sum(parts))
    diff = s - float(total)
    return {"sum_parts": s, "total": float(total), "diff": diff,
            "ok": bool(abs(diff) <= tol * max(1.0, abs(float(total))))}


def metric_consistency(report, tol=1e-9):
    """Проверка внутренней непротиворечивости отчёта по метрикам.

    Ловит то, что санити-чек по суммам не ловит: ARPPU меньше ARPU,
    платящих больше пользователей, конверсия вне [0, 1], DAU выше MAU,
    выручка не сходится с ARPU × пользователи.
    """
    problems = []
    g = report.get
    users, payers = g("users"), g("payers")
    arpu, arppu, revenue = g("arpu"), g("arppu"), g("revenue")
    dau, wau, mau = g("dau"), g("wau"), g("mau")
    cr = g("conversion")

    if users is not None and payers is not None and payers > users:
        problems.append("payers > users")
    if arpu is not None and arppu is not None and arppu < arpu - tol:
        problems.append("arppu < arpu")
    if cr is not None and not (0 <= cr <= 1 + tol):
        problems.append("conversion вне [0, 1]")
    if dau is not None and mau is not None and dau > mau + tol:
        problems.append("dau > mau")
    if dau is not None and wau is not None and dau > wau + tol:
        problems.append("dau > wau")
    if wau is not None and mau is not None and wau > mau + tol:
        problems.append("wau > mau")
    if revenue is not None and arpu is not None and users:
        if abs(revenue - arpu * users) > max(tol, 1e-6 * abs(revenue)):
            problems.append("revenue != arpu * users")
    return {"ok": len(problems) == 0, "problems": problems}
