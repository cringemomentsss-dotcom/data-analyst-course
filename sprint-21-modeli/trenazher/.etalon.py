"""Эталонные решения тренажёра спринта 21. Не подглядывать до решения."""

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import roc_auc_score, silhouette_score
from sklearn.preprocessing import StandardScaler


# --- выбор модели ----------------------------------------------------------

def choose_model_family(n_rows, n_features, need_interpretable=False,
                        has_categorical=True, need_probability=True):
    """Семейство модели под задачу и ограничения."""
    if need_interpretable:
        return {"family": "логистическая регрессия",
                "reason": "коэффициенты читаются напрямую и объясняются "
                          "человеку без ML",
                "interpretable": True,
                "caveat": "требует масштабирования и линейности по логиту; "
                          "взаимодействия признаков надо добавлять руками"}
    if n_rows < 1000:
        return {"family": "логистическая регрессия",
                "reason": f"{n_rows} строк — бустинг переобучится",
                "interpretable": True,
                "caveat": "на малой выборке любая метрика — оценка с большой "
                          "погрешностью"}
    if n_rows > 100_000 or n_features > 50:
        return {"family": "градиентный бустинг",
                "reason": "лучшее качество на табличных данных; сам берёт "
                          "нелинейности и взаимодействия",
                "interpretable": False,
                "caveat": "дольше учится, требует подбора, объясняется только "
                          "через SHAP"}
    return {"family": "случайный лес",
            "reason": "работает почти без настройки, устойчив к выбросам и "
                      "масштабу",
            "interpretable": False,
            "caveat": "хуже бустинга по качеству, важность признаков обманчива"}


def class_imbalance(y, severe=0.1):
    """Оценка дисбаланса классов."""
    a = np.asarray(y).astype(int)
    n = len(a)
    if n == 0:
        return None
    pos = int(a.sum())
    rate = pos / n
    minority = min(rate, 1 - rate)
    return {"n": n, "positives": pos, "negatives": n - pos,
            "positive_rate": float(rate), "minority_rate": float(minority),
            "ratio": float(max(pos, n - pos) / max(min(pos, n - pos), 1)),
            "severe": bool(minority < severe),
            "note": "accuracy бесполезна, смотри PR-AUC и recall"
                    if minority < severe else "классы сопоставимы"}


def resample_plan(y, method="class_weight"):
    """Что делать с дисбалансом."""
    a = np.asarray(y).astype(int)
    pos, neg = int(a.sum()), int(len(a) - a.sum())
    if method == "class_weight":
        return {"method": "class_weight", "keeps_all_data": True,
                "weights": {0: len(a) / (2 * max(neg, 1)),
                            1: len(a) / (2 * max(pos, 1))},
                "reason": "ничего не выбрасывается и не выдумывается; "
                          "первое, что стоит попробовать"}
    if method == "undersample":
        keep = min(pos, neg)
        return {"method": "undersample", "keeps_all_data": False,
                "rows_after": 2 * keep, "rows_dropped": len(a) - 2 * keep,
                "reason": "быстро учится",
                "warning": f"выбрасывается {len(a) - 2 * keep} строк "
                           "большинства — вместе с информацией"}
    if method == "oversample":
        target = max(pos, neg)
        return {"method": "oversample", "keeps_all_data": True,
                "rows_after": 2 * target,
                "rows_added": 2 * target - len(a),
                "reason": "данные не теряются",
                "warning": "копии редкого класса усиливают переобучение; "
                           "делать ТОЛЬКО внутри обучающего фолда"}
    raise ValueError(f"неизвестный метод: {method}")


# --- отток -----------------------------------------------------------------

def define_churn(activity, cutoff, horizon_days, user_col="user_id",
                 ts_col="ts", min_history_days=0):
    """Отток: не было активности в окне [cutoff, cutoff + horizon).

    В выборку берутся только те, кто был активен ДО отсечки.
    """
    a = activity[[user_col, ts_col]].copy()
    a[ts_col] = pd.to_datetime(a[ts_col])
    cut = pd.Timestamp(cutoff)
    end = cut + pd.Timedelta(days=horizon_days)

    past = a[a[ts_col] < cut]
    hist = past.groupby(user_col)[ts_col].agg(["min", "max"])
    if min_history_days:
        hist = hist[(cut - hist["min"]).dt.days >= min_history_days]
    future = set(a.loc[(a[ts_col] >= cut) & (a[ts_col] < end), user_col])

    out = pd.DataFrame({user_col: hist.index,
                        "last_seen": hist["max"].values,
                        "first_seen": hist["min"].values})
    out["churned"] = (~out[user_col].isin(future)).astype(int)
    return {"table": out.reset_index(drop=True),
            "n": int(len(out)), "churned": int(out["churned"].sum()),
            "rate": float(out["churned"].mean()) if len(out) else None,
            "cutoff": cut, "horizon_end": end,
            "definition": f"ни одной активности в {horizon_days} дней "
                          f"после {cut.date()}"}


def rfm_features(orders, cutoff, user_col="user_id", ts_col="ts",
                 amount_col="amount"):
    """Recency, Frequency, Monetary на момент отсечки."""
    o = orders[[user_col, ts_col, amount_col]].copy()
    o[ts_col] = pd.to_datetime(o[ts_col])
    cut = pd.Timestamp(cutoff)
    o = o[o[ts_col] < cut]
    g = o.groupby(user_col)
    out = pd.DataFrame({
        "recency_days": (cut - g[ts_col].max()).dt.days,
        "frequency": g.size(),
        "monetary": g[amount_col].sum(),
    })
    out["avg_check"] = out["monetary"] / out["frequency"]
    out["tenure_days"] = (cut - g[ts_col].min()).dt.days
    return out.reset_index()


def retention_value(prob_churn, ltv, retention_cost, success_rate=0.3):
    """Стоит ли удерживать клиента с такой вероятностью оттока."""
    p = float(prob_churn)
    expected_gain = p * float(success_rate) * float(ltv)
    value = expected_gain - float(retention_cost)
    return {"prob_churn": p, "expected_gain": expected_gain,
            "cost": float(retention_cost), "value": value,
            "worth_it": bool(value > 0),
            "breakeven_prob": float(retention_cost / (success_rate * ltv))
            if success_rate * ltv else None}


def churn_threshold(y_true, y_proba, ltv, retention_cost, success_rate=0.3,
                    steps=101):
    """Порог, максимизирующий прибыль от кампании удержания."""
    y = np.asarray(y_true).astype(int)
    p = np.asarray(y_proba, dtype=float)
    rows = []
    for t in np.linspace(0.0, 1.0, steps):
        targeted = p >= t
        saved = int((targeted & (y == 1)).sum()) * success_rate * ltv
        cost = int(targeted.sum()) * retention_cost
        rows.append({"threshold": float(t), "targeted": int(targeted.sum()),
                     "true_churners": int((targeted & (y == 1)).sum()),
                     "value": float(saved - cost)})
    curve = pd.DataFrame(rows)
    best = curve.loc[curve["value"].idxmax()].to_dict()
    return {"best": best, "curve": curve,
            "value_at_half": float(curve.loc[
                (curve["threshold"] - 0.5).abs().idxmin(), "value"])}


# --- интерпретация ---------------------------------------------------------

def logreg_interpret(feature_names, coefficients, top=5):
    """Коэффициенты логистической регрессии в человеческом виде."""
    rows = []
    for name, c in zip(feature_names, coefficients):
        c = float(c)
        rows.append({"feature": name, "coef": c,
                     "odds_ratio": float(np.exp(c)),
                     "direction": "повышает риск" if c > 0 else "снижает риск",
                     "effect_pct": float((np.exp(c) - 1) * 100)})
    rows.sort(key=lambda r: -abs(r["coef"]))
    return {"all": rows, "top": rows[:top],
            "note": "коэффициенты сравнимы между собой ТОЛЬКО если признаки "
                    "отмасштабированы; иначе величина отражает единицы "
                    "измерения, а не важность"}


def importance_caveats(importances, feature_names, cardinalities=None,
                       correlated_groups=None):
    """Почему встроенная важность признаков у деревьев обманчива."""
    warnings = []
    if cardinalities:
        high = [f for f in feature_names if cardinalities.get(f, 0) > 20]
        if high:
            warnings.append(
                f"признаки с большим числом значений ({', '.join(sorted(high))}) "
                "получают завышенную важность: у дерева больше способов "
                "разрезать по ним")
    if correlated_groups:
        for grp in correlated_groups:
            warnings.append(
                f"важность размазана между коррелирующими признаками "
                f"({', '.join(sorted(grp))}): каждый выглядит слабее, чем есть")
    total = float(np.sum(importances))
    rows = sorted(zip(feature_names, [float(i) for i in importances]),
                  key=lambda t: -t[1])
    return {"ranking": [{"feature": f, "importance": v} for f, v in rows],
            "sums_to_one": bool(abs(total - 1.0) < 1e-6),
            "warnings": warnings,
            "advice": "для выводов используй permutation importance или SHAP: "
                      "они меряют влияние на КАЧЕСТВО, а не частоту разрезов"}


def permutation_importance_manual(model, X, y, feature, n_repeats=5, seed=0):
    """Честная важность: насколько падает качество, если признак испортить."""
    rng = np.random.default_rng(seed)
    base = roc_auc_score(y, model.predict_proba(X)[:, 1])
    drops = []
    for _ in range(n_repeats):
        Xp = X.copy()
        Xp[feature] = rng.permutation(Xp[feature].values)
        drops.append(base - roc_auc_score(y, model.predict_proba(Xp)[:, 1]))
    return {"feature": feature, "baseline_auc": float(base),
            "mean_drop": float(np.mean(drops)), "std_drop": float(np.std(drops)),
            "matters": bool(np.mean(drops) > 0.01)}


def explain_prediction(feature_values, contributions, base_rate, top=3):
    """Объяснение одного прогноза словами."""
    rows = [{"feature": f, "value": feature_values.get(f), "contribution": float(c)}
            for f, c in contributions.items()]
    rows.sort(key=lambda r: -abs(r["contribution"]))
    total = float(sum(r["contribution"] for r in rows))
    parts = []
    for r in rows[:top]:
        word = "повышает" if r["contribution"] > 0 else "снижает"
        parts.append(f"{r['feature']} = {r['value']} {word} риск")
    return {"base_rate": float(base_rate),
            "prediction": float(base_rate + total),
            "top_factors": rows[:top],
            "text": "; ".join(parts) if parts else "значимых факторов нет"}


# --- регрессия -------------------------------------------------------------

def residual_analysis(y_true, y_pred, n_bins=5):
    """Что остатки говорят о качестве модели."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    res = y - p
    df = pd.DataFrame({"pred": p, "res": res})
    df["bin"] = pd.qcut(df["pred"], q=min(n_bins, df["pred"].nunique()),
                        duplicates="drop")
    by_bin = df.groupby("bin", observed=True)["res"].agg(["mean", "std", "size"])
    problems = []
    if abs(float(res.mean())) > 0.05 * (np.std(y) or 1):
        problems.append("остатки смещены: модель систематически ошибается "
                        "в одну сторону")
    stds = by_bin["std"].dropna()
    if len(stds) > 1 and stds.max() / max(stds.min(), 1e-9) > 3:
        problems.append("разброс остатков растёт с величиной прогноза "
                        "(гетероскедастичность): для больших значений модель "
                        "менее надёжна")
    means = by_bin["mean"].dropna()
    if len(means) > 2 and (means.iloc[0] * means.iloc[-1] < 0):
        problems.append("остатки меняют знак по краям: связь нелинейна")
    return {"mean_residual": float(res.mean()), "std_residual": float(res.std()),
            "by_bin": by_bin, "problems": problems, "ok": len(problems) == 0}


def vif_check(df, columns=None, threshold=5.0):
    """Мультиколлинеарность через VIF."""
    from sklearn.linear_model import LinearRegression
    cols = list(columns) if columns else [
        c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    rows = []
    for c in cols:
        others = [o for o in cols if o != c]
        if not others:
            continue
        r2 = LinearRegression().fit(df[others], df[c]).score(df[others], df[c])
        vif = 1 / (1 - r2) if r2 < 1 else float("inf")
        rows.append({"feature": c, "r2": float(r2), "vif": float(vif),
                     "problem": bool(vif >= threshold)})
    rows.sort(key=lambda r: -r["vif"])
    bad = [r["feature"] for r in rows if r["problem"]]
    return {"table": rows, "problematic": bad, "ok": len(bad) == 0,
            "note": "мультиколлинеарность не портит ПРОГНОЗ, но делает "
                    "коэффициенты неустойчивыми: интерпретировать их нельзя"}


# --- кластеризация ---------------------------------------------------------

def scale_for_clustering(df, columns, log_columns=None):
    """Подготовка признаков к кластеризации.

    Масштабирование обязательно: K-Means работает на расстояниях.
    Логарифм — для признаков с длинным хвостом, иначе кластеры соберутся
    вокруг выбросов.
    """
    cols = list(columns)
    X = df[cols].astype(float).copy()
    logged = list(log_columns or [])
    for c in logged:
        if c in X.columns:
            X[c] = np.log1p(X[c].clip(lower=0))
    scaler = StandardScaler()
    arr = scaler.fit_transform(X)
    return {"array": arr, "columns": cols, "logged": logged,
            "scaler": scaler,
            "note": "без масштабирования признак в рублях полностью определит "
                    "кластеры, а признак в долях не повлияет ни на что"}


def elbow_and_silhouette(X, k_range=(2, 7), seed=42, sample_size=None):
    """Инерция и силуэт по числу кластеров."""
    rows = []
    for k in range(k_range[0], k_range[1]):
        km = KMeans(n_clusters=k, random_state=seed, n_init=10).fit(X)
        kw = {"sample_size": sample_size, "random_state": seed} if sample_size else {}
        sil = silhouette_score(X, km.labels_, **kw)
        rows.append({"k": k, "inertia": float(km.inertia_),
                     "silhouette": float(sil)})
    t = pd.DataFrame(rows)
    best_sil = int(t.loc[t["silhouette"].idxmax(), "k"])
    return {"table": t, "best_by_silhouette": best_sil,
            "note": "силуэт часто максимален при малом k, а на данных без "
                    "структуры растёт с k. Ни то ни другое не значит, что "
                    "столько сегментов полезно: метрика оценивает геометрию, "
                    "а число сегментов выбирает бизнес"}


def describe_clusters(df, labels, columns, target=None):
    """Характеристики кластеров: медианы признаков и размер."""
    d = df.copy()
    d["_cluster"] = labels
    agg = {c: "median" for c in columns}
    out = d.groupby("_cluster").agg(size=("_cluster", "size"), **{
        c: (c, "median") for c in columns})
    if target is not None:
        out[target] = d.groupby("_cluster")[target].mean()
    out["share"] = out["size"] / len(d)
    return out.reset_index().rename(columns={"_cluster": "cluster"})


def name_clusters(profile, rules):
    """Проверка осмысленности кластеров и присвоение имён.

    rules — [(имя, функция от строки профиля)]. Кластер, под который не
    подошло ни одно правило, остаётся безымянным — и это сигнал.
    """
    named, unnamed = [], []
    for _, row in profile.iterrows():
        label = None
        for name, cond in rules:
            if cond(row):
                label = name
                break
        entry = {"cluster": int(row["cluster"]), "name": label,
                 "size": int(row["size"])}
        (named if label else unnamed).append(entry)
    return {"named": named, "unnamed": unnamed,
            "all_named": len(unnamed) == 0,
            "verdict": "кластеры описываются словами" if not unnamed else
                       "часть кластеров не описывается словами — такая "
                       "сегментация бесполезна: бизнес не сможет с ней работать"}


def rfm_segments(rfm, r_col="recency_days", f_col="frequency",
                 m_col="monetary", bins=3):
    """RFM-сегментация без ML: квантили по трём осям."""
    d = rfm.copy()
    d["R"] = pd.qcut(d[r_col].rank(method="first"), bins,
                     labels=range(bins, 0, -1)).astype(int)
    d["F"] = pd.qcut(d[f_col].rank(method="first"), bins,
                     labels=range(1, bins + 1)).astype(int)
    d["M"] = pd.qcut(d[m_col].rank(method="first"), bins,
                     labels=range(1, bins + 1)).astype(int)
    d["rfm"] = d["R"].astype(str) + d["F"].astype(str) + d["M"].astype(str)
    d["score"] = d[["R", "F", "M"]].sum(axis=1)
    top = int(3 * bins)
    d["segment"] = np.where(d["score"] >= top - 1, "чемпионы",
                    np.where(d["R"] == 1, "потерянные",
                     np.where(d["score"] <= bins + 1, "спящие", "середина")))
    return {"table": d, "counts": d["segment"].value_counts().to_dict(),
            "note": "RFM не требует обучения, объясняется за минуту и "
                    "воспроизводится где угодно. Прежде чем кластеризовать, "
                    "проверь, не хватает ли его"}


# --- модель в проде --------------------------------------------------------

def psi(expected, actual, bins=10):
    """Population Stability Index: насколько распределение уехало."""
    e = pd.Series(expected).dropna().astype(float)
    a = pd.Series(actual).dropna().astype(float)
    edges = np.unique(np.quantile(e, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return None
    e_share = np.histogram(e, bins=edges)[0] / len(e)
    a_share = np.histogram(a, bins=edges)[0] / len(a)
    eps = 1e-6
    e_share = np.clip(e_share, eps, None)
    a_share = np.clip(a_share, eps, None)
    value = float(np.sum((a_share - e_share) * np.log(a_share / e_share)))
    if value < 0.1:
        verdict, action = "стабильно", ""
    elif value < 0.25:
        verdict, action = "заметный сдвиг", "проверить признак и качество модели"
    else:
        verdict, action = "сильный сдвиг", "модель переобучить, прогнозам не верить"
    return {"psi": value, "verdict": verdict, "action": action,
            "bins": len(edges) - 1}
