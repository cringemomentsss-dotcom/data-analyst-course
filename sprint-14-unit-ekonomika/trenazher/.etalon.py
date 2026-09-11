"""Эталонные решения тренажёра спринта 14. Не подглядывать до решения."""

import math
import re

import numpy as np
import pandas as pd


# --- база ------------------------------------------------------------------

def unit_pnl(revenue, cogs, marketing=0.0, units=1):
    """P&L одного юнита: маржа до маркетинга и после."""
    if units <= 0:
        raise ValueError("units должно быть больше нуля")
    rev, cost, mkt = float(revenue), float(cogs), float(marketing)
    gross = rev - cost
    contrib = gross - mkt
    return {"units": int(units),
            "revenue_per_unit": rev / units,
            "cogs_per_unit": cost / units,
            "gross_margin": gross,
            "gross_margin_pct": 100 * gross / rev if rev else None,
            "contribution_margin": contrib,
            "contribution_per_unit": contrib / units,
            "profitable": bool(contrib > 0)}


def cac_by_channel(spend, acquired, channel_col="channel", cost_col="cost",
                   n_col="n"):
    """CAC по каналам. Каналы без расходов и расходы без привлечений остаются."""
    s = spend.groupby(channel_col, as_index=False)[cost_col].sum()
    a = acquired.groupby(channel_col, as_index=False)[n_col].sum()
    m = s.merge(a, on=channel_col, how="outer")
    m[n_col] = m[n_col].fillna(0).astype(int)
    m[cost_col] = m[cost_col].astype(float)
    has_cost = m[cost_col].notna()
    m["cac"] = np.where(has_cost & (m[n_col] > 0),
                        m[cost_col] / m[n_col].replace(0, np.nan), np.nan)
    m["cac"] = m["cac"].astype(float)
    m["note"] = ""
    m.loc[has_cost & (m[n_col] == 0), "note"] = "расход без привлечений"
    m.loc[~has_cost & (m[n_col] > 0), "note"] = "нет данных о расходе"
    return m.sort_values(channel_col).reset_index(drop=True)


def breakeven_cac(arpu_per_period, margin, periods, discount=0.0):
    """Максимальный CAC, при котором канал окупается за periods периодов."""
    if periods <= 0:
        raise ValueError("periods должно быть больше нуля")
    per = float(arpu_per_period) * float(margin)
    total = 0.0
    for t in range(int(periods)):
        total += per / ((1 + float(discount)) ** t)
    return {"margin_per_period": per, "periods": int(periods),
            "breakeven_cac": total,
            "undiscounted": per * int(periods)}


def payback_period(cac, margin_by_period):
    """За сколько периодов накопленная маржа перекроет CAC.

    Возвращает целое число периодов и дробную оценку с линейной
    интерполяцией внутри периода. Если не окупается — None.
    """
    cac = float(cac)
    cum = 0.0
    for i, m in enumerate(margin_by_period, start=1):
        prev = cum
        cum += float(m)
        if cum >= cac:
            need = cac - prev
            frac = (i - 1) + (need / float(m) if m else 0.0)
            return {"periods": i, "exact": float(frac),
                    "cumulative": cum, "cac": cac, "paid_back": True}
    return {"periods": None, "exact": None, "cumulative": cum, "cac": cac,
            "paid_back": False}


def ltv_horizon(arpu_per_period, retention_curve, margin=1.0):
    """LTV на горизонте: сумма ARPU × доля выживших × маржа по периодам."""
    r = [float(x) for x in retention_curve]
    per = [float(arpu_per_period) * x * float(margin) for x in r]
    cum = np.cumsum(per)
    return {"horizon": len(r), "ltv": float(cum[-1]) if len(cum) else 0.0,
            "by_period": [float(x) for x in per],
            "cumulative": [float(x) for x in cum]}


# --- когорты ---------------------------------------------------------------

def cohort_unit_economics(cohorts, cac_col="cac", size_col="size",
                          revenue_cols=None, margin=1.0):
    """Юнит-экономика по когортам: накопленная маржа против CAC.

    revenue_cols — упорядоченный список столбцов выручки по периодам.
    Возвращает DataFrame с накопленной маржой на юнит, LTV/CAC и признаком
    окупаемости на последнем горизонте.
    """
    df = cohorts.copy()
    if revenue_cols is None:
        revenue_cols = [c for c in df.columns
                        if c not in (cac_col, size_col) and df[c].dtype.kind in "if"]
    out = df[[c for c in df.columns if c in (cac_col, size_col)]].copy()
    if size_col in df.columns:
        out[size_col] = df[size_col]
    cum = np.zeros(len(df), dtype=float)
    for c in revenue_cols:
        cum = cum + df[c].astype(float).to_numpy() * float(margin)
        out[f"cum_{c}"] = cum
    out["cac"] = df[cac_col].astype(float)
    out["ltv_cac"] = out[f"cum_{revenue_cols[-1]}"] / out["cac"].replace(0, np.nan)
    out["paid_back"] = out[f"cum_{revenue_cols[-1]}"] >= out["cac"]
    return out


def convergence_check(cohort_table, ltv_col="ltv_cac", target=1.0):
    """Сходимость юнит-экономики: сколько когорт вышли в плюс."""
    x = pd.to_numeric(cohort_table[ltv_col], errors="coerce").dropna()
    n = len(x)
    ok = int((x >= target).sum())
    return {"cohorts": n, "converged": ok,
            "share": ok / n if n else None,
            "worst": float(x.min()) if n else None,
            "best": float(x.max()) if n else None,
            "median": float(x.median()) if n else None,
            "converged_overall": bool(ok == n)}


def weighted_vs_cohort(cohort_table, size_col="size", ltv_col="ltv",
                       cac_col="cac"):
    """Средневзвешенная юнит-экономика против покогортной.

    Показывает случай, когда «в среднем прибыльно», а по каждой когорте нет,
    и наоборот: когда средняя картина хуже, чем у большинства когорт.
    """
    df = cohort_table
    w = df[size_col].astype(float).to_numpy()
    ltv = df[ltv_col].astype(float).to_numpy()
    cac = df[cac_col].astype(float).to_numpy()
    total_w = w.sum()
    if total_w == 0:
        return None
    avg_ltv = float((ltv * w).sum() / total_w)
    avg_cac = float((cac * w).sum() / total_w)
    per_cohort = ltv / np.where(cac == 0, np.nan, cac)
    profitable = int(np.nansum(per_cohort >= 1.0))
    return {"weighted_ltv": avg_ltv, "weighted_cac": avg_cac,
            "weighted_ltv_cac": avg_ltv / avg_cac if avg_cac else None,
            "weighted_profitable": bool(avg_ltv >= avg_cac),
            "cohorts": int(len(df)), "cohorts_profitable": profitable,
            "misleading": bool((avg_ltv >= avg_cac) and profitable < len(df))}


# --- поправки к выручке ----------------------------------------------------

def expected_ggr(bets, stake_col="stake", rtp_col="rtp"):
    """Ожидаемый GGR: оборот × (1 − RTP). RTP в процентах."""
    b = bets[[stake_col, rtp_col]].copy()
    stake = pd.to_numeric(b[stake_col], errors="coerce").fillna(0.0)
    rtp = pd.to_numeric(b[rtp_col], errors="coerce").fillna(0.0) / 100.0
    turnover = float(stake.sum())
    exp = float((stake * (1 - rtp)).sum())
    return {"turnover": turnover, "expected_ggr": exp,
            "expected_hold_pct": 100 * exp / turnover if turnover else None,
            "n_bets": int(len(b))}


def ggr_confidence(stake_total, hold_pct, n_bets, avg_stake=None, z=1.96):
    """Насколько фактический GGR может отличаться от ожидаемого случайно.

    Грубая, но рабочая оценка: исход одной ставки считается величиной со
    стандартным отклонением порядка её размера, поэтому разброс суммы
    растёт как корень из числа ставок.
    """
    n = int(n_bets)
    if n <= 0:
        return None
    stake_total = float(stake_total)
    avg = float(avg_stake) if avg_stake else stake_total / n
    exp = stake_total * float(hold_pct) / 100.0
    sd = avg * math.sqrt(n)
    return {"expected_ggr": exp, "sd": sd,
            "lo": exp - z * sd, "hi": exp + z * sd,
            "sd_to_expected": sd / exp if exp else None,
            "reliable": bool(exp > z * sd)}


def bonus_real_cost(bonuses, bets, bonus_id_col="bonus_id",
                    user_col="user_id", amount_col="amount",
                    wager_col="wager_multiplier", status_col="status",
                    granted_col="granted_ts", completed_col="completed_ts",
                    bet_ts_col="ts", stake_col="stake"):
    """Реальная стоимость бонусов с проверкой отыгрыша.

    Начисленный бонус — не расход. Расход — бонус, который дошёл до
    вывода. Статус 'completed' проверяется по фактическому обороту
    в окне между начислением и закрытием.
    """
    b = bonuses.copy()
    b[granted_col] = pd.to_datetime(b[granted_col])
    b[completed_col] = pd.to_datetime(b[completed_col])
    e = bets[[user_col, bet_ts_col, stake_col]].copy()
    e[bet_ts_col] = pd.to_datetime(e[bet_ts_col])

    rows = []
    for _, r in b.iterrows():
        end = r[completed_col]
        if pd.isna(end):
            end = e[bet_ts_col].max()
        mask = ((e[user_col] == r[user_col]) & (e[bet_ts_col] >= r[granted_col])
                & (e[bet_ts_col] <= end))
        staked = float(e.loc[mask, stake_col].sum())
        required = float(r[amount_col]) * float(r[wager_col])
        rows.append({bonus_id_col: r[bonus_id_col],
                     "status": r[status_col],
                     "amount": float(r[amount_col]),
                     "required": required, "staked": staked,
                     "wager_met": bool(staked >= required)})
    d = pd.DataFrame(rows)
    granted = float(d["amount"].sum())
    claimed = float(d.loc[d["status"] == "completed", "amount"].sum())
    real = float(d.loc[(d["status"] == "completed") & d["wager_met"],
                       "amount"].sum())
    n_claimed = int((d["status"] == "completed").sum())
    n_real = int(((d["status"] == "completed") & d["wager_met"]).sum())
    return {"granted": granted, "claimed_completed": claimed,
            "verified_cost": real,
            "n_completed": n_claimed, "n_verified": n_real,
            "status_reliable": bool(n_claimed == n_real),
            "overstated_by": claimed - real,
            "detail": d}


def normalize_channel(values, synonyms=None):
    """Нормализация названия канала: регистр, пробелы, разделители, синонимы."""
    syn = {k.lower(): v for k, v in (synonyms or {}).items()}
    out = []
    for v in values:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            out.append("unknown")
            continue
        s = str(v).strip().lower()
        s = re.sub(r"[\s\-]+", "_", s)
        s = re.sub(r"_+", "_", s).strip("_")
        if s == "":
            s = "unknown"
        out.append(syn.get(s, s))
    return out


# --- точки роста -----------------------------------------------------------

def metric_gap_decomposition(base, actual):
    """Разложение изменения произведения на вклад каждого множителя.

    base и actual — словари с одинаковыми ключами. Метод последовательной
    замены: множители подставляются по одному в порядке ключей, вклад
    каждого — прирост произведения на его шаге. Сумма вкладов точно
    равна общему изменению.
    """
    keys = list(base)
    if set(keys) != set(actual):
        raise ValueError("наборы множителей не совпадают")
    cur = dict(base)
    prod = lambda d: float(np.prod([float(d[k]) for k in keys]))
    start, end = prod(base), prod(actual)
    contrib = {}
    prev = start
    for k in keys:
        cur[k] = actual[k]
        now = prod(cur)
        contrib[k] = now - prev
        prev = now
    total = end - start
    return {"base": start, "actual": end, "total_change": total,
            "contribution": contrib,
            "share": {k: (v / total if total else None) for k, v in contrib.items()},
            "biggest": max(contrib, key=lambda k: abs(contrib[k])) if contrib else None}


def rice_score(reach, impact, confidence, effort):
    """RICE = Reach × Impact × Confidence / Effort."""
    effort = float(effort)
    if effort <= 0:
        raise ValueError("effort должно быть больше нуля")
    c = float(confidence)
    if c > 1:
        c = c / 100.0
    score = float(reach) * float(impact) * c / effort
    return {"reach": float(reach), "impact": float(impact),
            "confidence": c, "effort": effort, "score": score}


def ice_score(impact, confidence, ease):
    """ICE = среднее геометрическое трёх оценок по шкале 1..10."""
    vals = [float(impact), float(confidence), float(ease)]
    for v in vals:
        if not (1 <= v <= 10):
            raise ValueError("оценки ICE задаются по шкале от 1 до 10")
    score = float(np.prod(vals)) ** (1 / 3)
    return {"impact": vals[0], "confidence": vals[1], "ease": vals[2],
            "score": score}


def potential_estimate(users_at_step, current_cr, target_cr, value_per_conv,
                       capture=0.5):
    """Потенциал шага воронки при консервативном захвате разрыва."""
    if not (0 <= capture <= 1):
        raise ValueError("capture — доля от 0 до 1")
    gap = float(target_cr) - float(current_cr)
    if gap <= 0:
        return {"gap": gap, "extra_conversions": 0.0, "value": 0.0,
                "capture": float(capture), "worth_doing": False}
    extra = float(users_at_step) * gap * float(capture)
    return {"gap": gap, "extra_conversions": extra,
            "value": extra * float(value_per_conv),
            "capture": float(capture),
            "worth_doing": bool(extra * float(value_per_conv) > 0)}


def segment_opportunity(segments, n_col="n", cr_col="cr", value_col="value",
                        benchmark=None, capture=0.5):
    """Поиск сегмента с наибольшим АБСОЛЮТНЫМ потенциалом, а не худшей конверсией.

    Бенчмарк по умолчанию — лучшая конверсия среди сегментов.
    """
    df = segments.copy()
    bench = float(benchmark) if benchmark is not None else float(df[cr_col].max())
    df["gap"] = bench - df[cr_col].astype(float)
    df["gap"] = df["gap"].clip(lower=0)
    df["extra"] = df[n_col].astype(float) * df["gap"] * float(capture)
    df["potential"] = df["extra"] * df[value_col].astype(float)
    df = df.sort_values("potential", ascending=False).reset_index(drop=True)
    worst_cr = segments.loc[segments[cr_col].astype(float).idxmin()]
    return {"benchmark": bench, "table": df,
            "top_by_potential": df.iloc[0].to_dict() if len(df) else None,
            "worst_by_cr": worst_cr.to_dict(),
            "same": bool(len(df) and df.iloc[0][cr_col] == worst_cr[cr_col])}


def sensitivity_range(func, assumptions, spreads):
    """Насколько вывод чувствителен к допущениям.

    func принимает словарь допущений и возвращает число. spreads —
    словарь {ключ: (низкое, высокое)}. Возвращает базовое значение,
    границы при одиночном изменении каждого допущения и самое влиятельное.
    """
    base = float(func(dict(assumptions)))
    rows = []
    for k, (lo, hi) in spreads.items():
        a = dict(assumptions)
        a[k] = lo
        v_lo = float(func(a))
        a = dict(assumptions)
        a[k] = hi
        v_hi = float(func(a))
        rows.append({"assumption": k, "low": v_lo, "high": v_hi,
                     "swing": abs(v_hi - v_lo)})
    t = pd.DataFrame(rows).sort_values("swing", ascending=False).reset_index(drop=True)
    return {"base": base, "table": t,
            "most_influential": t.iloc[0]["assumption"] if len(t) else None,
            "flips_sign": bool(len(t) and
                               ((t["low"] * base < 0).any() or (t["high"] * base < 0).any()))}
