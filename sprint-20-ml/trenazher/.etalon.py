"""Эталонные решения тренажёра спринта 20. Не подглядывать до решения."""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import (accuracy_score, average_precision_score, f1_score,
                             mean_absolute_error, precision_score, r2_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

SCALE_SENSITIVE = {"logreg", "svm", "knn", "kmeans", "pca", "ridge", "lasso",
                   "neural_net"}
SCALE_FREE = {"tree", "random_forest", "gradient_boosting", "xgboost",
              "lightgbm", "catboost", "naive_bayes"}


# --- постановка ------------------------------------------------------------

def define_target(events, users, event_col="event", ts_col="ts",
                  user_col="user_id", reg_col="reg_date",
                  target_event="deposit", window_days=30):
    """Целевая переменная с явным окном наблюдения.

    Единица — пользователь. Цель равна единице, если целевое событие
    произошло в окне [reg_date, reg_date + window_days).
    """
    u = users[[user_col, reg_col]].copy()
    u[reg_col] = pd.to_datetime(u[reg_col])
    e = events[[user_col, event_col, ts_col]].copy()
    e[ts_col] = pd.to_datetime(e[ts_col])
    e = e[e[event_col] == target_event]
    m = u.merge(e, on=user_col, how="left")
    inside = (m[ts_col] >= m[reg_col]) & (
        m[ts_col] < m[reg_col] + pd.Timedelta(days=window_days))
    m["hit"] = inside.fillna(False)
    agg = m.groupby(user_col, as_index=False)["hit"].max()
    out = u.merge(agg, on=user_col, how="left")
    out["y"] = out["hit"].fillna(False).astype(int)
    out = out.drop(columns=["hit"])
    return {"table": out, "n": int(len(out)), "positives": int(out["y"].sum()),
            "rate": float(out["y"].mean()) if len(out) else None,
            "window_days": int(window_days),
            "definition": f"{target_event} в первые {window_days} дней "
                          f"после регистрации"}


def check_observation_window(users, data_end, reg_col="reg_date",
                             window_days=30):
    """Кому окно наблюдения ещё не закрылось.

    Пользователь, зарегистрировавшийся позже чем за window_days до конца
    данных, ещё мог совершить целевое действие. Его нельзя размечать
    нулём — его вообще нельзя брать в выборку.
    """
    u = users.copy()
    u[reg_col] = pd.to_datetime(u[reg_col])
    end = pd.Timestamp(data_end)
    cutoff = end - pd.Timedelta(days=window_days)
    incomplete = u[u[reg_col] > cutoff]
    return {"total": int(len(u)), "cutoff": cutoff,
            "incomplete": int(len(incomplete)),
            "usable": int(len(u) - len(incomplete)),
            "share_incomplete": float(len(incomplete) / len(u)) if len(u) else None,
            "advice": "этих пользователей исключают из обучающей выборки: "
                      "их ноль означает «ещё не успел», а не «не сделает»"}


def baseline_scores(y_true, rule_pred=None):
    """Метрики тупых базовых решений, с которыми сравнивают модель."""
    y = np.asarray(y_true).astype(int)
    rate = float(y.mean()) if len(y) else None
    const = np.full(len(y), rate if rate is not None else 0.0)
    out = {"positive_rate": rate,
           "constant": {"roc_auc": 0.5,
                        "pr_auc": float(average_precision_score(y, const))
                        if len(set(y)) > 1 else None,
                        "accuracy_all_zero": float(1 - rate) if rate is not None else None}}
    if rule_pred is not None:
        r = np.asarray(rule_pred).astype(int)
        out["rule"] = {"roc_auc": float(roc_auc_score(y, r)),
                       "pr_auc": float(average_precision_score(y, r)),
                       "accuracy": float(accuracy_score(y, r)),
                       "precision": float(precision_score(y, r, zero_division=0)),
                       "recall": float(recall_score(y, r, zero_division=0))}
    out["note"] = ("модель, не обогнавшая эти числа, не нужна: "
                   "константа и правило в одну строку стоят ноль")
    return out


# --- утечка и разделение ---------------------------------------------------

def leak_scan(df, target_col, feature_cols=None, corr_threshold=0.95,
              auc_threshold=0.95, state_suffixes=("_status", "_flag", "is_",
                                                  "_level", "_total", "_ever")):
    """Поиск признаков, подозрительных на утечку целевой переменной."""
    y = df[target_col].astype(float)
    cols = list(feature_cols) if feature_cols else [
        c for c in df.columns if c != target_col]
    findings = []
    for c in cols:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            x = s.astype(float)
            if x.nunique(dropna=True) <= 1:
                continue
            corr = abs(x.corr(y))
            if pd.notna(corr) and corr >= corr_threshold:
                findings.append({"feature": c, "reason": "почти полная корреляция "
                                 "с целевой переменной", "value": float(corr)})
                continue
            if y.nunique() > 1:
                auc = roc_auc_score(y, x.fillna(x.median()))
                auc = max(auc, 1 - auc)
                if auc >= auc_threshold:
                    findings.append({"feature": c,
                                     "reason": "один признак почти идеально "
                                               "разделяет классы",
                                     "value": float(auc)})
                    continue
        low = c.lower()
        if any(low.startswith(p) or low.endswith(p) for p in state_suffixes):
            findings.append({"feature": c,
                             "reason": "похоже на поле-состояние без отметки "
                                       "времени: неизвестно, каким оно было "
                                       "в момент прогноза",
                             "value": None})
    return {"findings": findings, "n": len(findings),
            "clean": len(findings) == 0,
            "suspicious": [f["feature"] for f in findings]}


def time_split(df, time_col, test_size=0.25):
    """Разделение по времени: обучаемся на прошлом, проверяемся на будущем."""
    d = df.copy()
    d[time_col] = pd.to_datetime(d[time_col])
    d = d.sort_values(time_col)
    cut = int(len(d) * (1 - test_size))
    train, test = d.iloc[:cut], d.iloc[cut:]
    return {"train": train, "test": test,
            "n_train": int(len(train)), "n_test": int(len(test)),
            "boundary": test[time_col].min() if len(test) else None,
            "reason": "случайное разделение на данных со временем даёт "
                      "утечку из будущего: модель учится на том, чего в "
                      "момент прогноза ещё не существовало"}


def split_sanity(train, test, id_col, target_col, time_col=None, tol=0.1):
    """Проверка корректности разделения."""
    problems = []
    overlap = set(train[id_col]) & set(test[id_col])
    if overlap:
        problems.append(f"{len(overlap)} объектов попали и в train, и в test")
    r_tr = float(train[target_col].mean())
    r_te = float(test[target_col].mean())
    if r_tr and abs(r_te - r_tr) / r_tr > tol:
        problems.append(f"доли класса разошлись: {r_tr:.3f} против {r_te:.3f}")
    if len(set(test[target_col])) < 2:
        problems.append("в тесте только один класс: метрики не считаются")
    leak_time = False
    if time_col:
        if pd.to_datetime(train[time_col]).max() > pd.to_datetime(test[time_col]).min():
            leak_time = True
            problems.append("train содержит объекты позже начала test")
    return {"overlap": len(overlap), "rate_train": r_tr, "rate_test": r_te,
            "time_leak": leak_time, "problems": problems,
            "ok": len(problems) == 0}


# --- признаки --------------------------------------------------------------

def encode_categorical(values, method="onehot", target=None):
    """Кодирование категориального признака."""
    s = pd.Series(list(values)).astype("object").fillna("__NA__")
    if method == "onehot":
        d = pd.get_dummies(s, prefix="c", dtype=int)
        return {"method": "onehot", "frame": d, "n_columns": int(d.shape[1]),
                "warning": "на признаке с большой кардинальностью даёт "
                           "сотни столбцов" if d.shape[1] > 20 else ""}
    if method == "label":
        cats = sorted(s.unique())
        mapping = {c: i for i, c in enumerate(cats)}
        return {"method": "label", "codes": [mapping[v] for v in s],
                "mapping": mapping,
                "warning": "создаёт ложный порядок: модель решит, что "
                           "категория 3 больше категории 1. Годится для "
                           "деревьев, вредна для линейных моделей"}
    if method == "target":
        if target is None:
            raise ValueError("для target encoding нужен target")
        t = pd.Series(list(target)).astype(float)
        means = t.groupby(s).mean()
        return {"method": "target", "codes": [float(means[v]) for v in s],
                "mapping": {k: float(v) for k, v in means.items()},
                "warning": "ПОСЧИТАН НА ВСЕЙ ВЫБОРКЕ — это утечка. "
                           "Считать только внутри фолдов кросс-валидации"}
    raise ValueError(f"неизвестный метод: {method}")


def target_encoding_leak(values, target, n_splits=5, seed=0):
    """Насколько target encoding без кросс-валидации завышает качество."""
    s = pd.Series(list(values)).astype("object")
    y = pd.Series(list(target)).astype(int)
    naive = s.map(y.groupby(s).mean()).astype(float)
    auc_naive = float(roc_auc_score(y, naive))

    oof = pd.Series(np.nan, index=s.index, dtype=float)
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    for tr, te in skf.split(s, y):
        means = y.iloc[tr].groupby(s.iloc[tr]).mean()
        oof.iloc[te] = s.iloc[te].map(means).astype(float).values
    oof = oof.fillna(y.mean())
    auc_oof = float(roc_auc_score(y, oof))
    return {"auc_naive": auc_naive, "auc_out_of_fold": auc_oof,
            "inflation": auc_naive - auc_oof,
            "leaks": bool(auc_naive - auc_oof > 0.02)}


def needs_scaling(model_kind):
    """Нужно ли масштабировать признаки для этой модели."""
    m = str(model_kind).lower()
    if m in SCALE_SENSITIVE:
        return {"model": m, "needs_scaling": True,
                "reason": "модель опирается на расстояния или на величину "
                          "коэффициентов: признак в рублях задавит признак в долях"}
    if m in SCALE_FREE:
        return {"model": m, "needs_scaling": False,
                "reason": "дерево сравнивает значения внутри одного признака, "
                          "масштаб ему безразличен"}
    raise ValueError(f"неизвестная модель: {model_kind}")


def missing_strategy(series, name="", threshold_drop=0.6, threshold_flag=0.05):
    """Что делать с пропусками в признаке."""
    s = pd.Series(list(series))
    share = float(s.isna().mean()) if len(s) else 0.0
    numeric = pd.api.types.is_numeric_dtype(s)
    if share == 0:
        strategy, reason = "ничего", "пропусков нет"
    elif share >= threshold_drop:
        strategy = "выбросить признак"
        reason = f"{share:.0%} пропусков: заполнять нечего"
    elif numeric:
        strategy = "медиана + флаг пропуска"
        reason = ("медиана устойчивее среднего; флаг сохраняет информацию о "
                  "самом факте пропуска, а он часто значим")
    else:
        strategy = "отдельная категория"
        reason = "пропуск в категории — это тоже категория, а не ошибка"
    return {"feature": name, "missing_share": share, "strategy": strategy,
            "add_flag": bool(threshold_flag <= share < threshold_drop),
            "reason": reason}


# --- метрики ---------------------------------------------------------------

def classification_metrics(y_true, y_proba, threshold=0.5):
    """Полный набор метрик классификации при заданном пороге."""
    y = np.asarray(y_true).astype(int)
    p = np.asarray(y_proba, dtype=float)
    pred = (p >= threshold).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    return {"threshold": float(threshold),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "accuracy": float(accuracy_score(y, pred)),
            "precision": float(precision_score(y, pred, zero_division=0)),
            "recall": float(recall_score(y, pred, zero_division=0)),
            "f1": float(f1_score(y, pred, zero_division=0)),
            "roc_auc": float(roc_auc_score(y, p)) if len(set(y)) > 1 else None,
            "pr_auc": float(average_precision_score(y, p)) if len(set(y)) > 1 else None}


def accuracy_trap(y_true, y_proba, threshold=0.5):
    """Сравнение accuracy модели с accuracy болвана, отвечающего «нет»."""
    y = np.asarray(y_true).astype(int)
    pred = (np.asarray(y_proba, dtype=float) >= threshold).astype(int)
    model_acc = float(accuracy_score(y, pred))
    dumb_acc = float(1 - y.mean())
    return {"model_accuracy": model_acc, "always_zero_accuracy": dumb_acc,
            "beats_dumb": bool(model_acc > dumb_acc),
            "positive_rate": float(y.mean()),
            "recall": float(recall_score(y, pred, zero_division=0)),
            "note": "на редком классе accuracy почти равна доле нулей: "
                    "болван, всегда отвечающий «нет», выглядит отличной моделью"}


def threshold_for_business(y_true, y_proba, cost_fp, cost_fn, gain_tp=0.0,
                           steps=101):
    """Порог, максимизирующий деньги, а не F1."""
    y = np.asarray(y_true).astype(int)
    p = np.asarray(y_proba, dtype=float)
    best = None
    rows = []
    for t in np.linspace(0.0, 1.0, steps):
        pred = (p >= t).astype(int)
        tp = int(((pred == 1) & (y == 1)).sum())
        fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum())
        value = gain_tp * tp - cost_fp * fp - cost_fn * fn
        rows.append({"threshold": float(t), "value": float(value),
                     "tp": tp, "fp": fp, "fn": fn})
        if best is None or value > best["value"]:
            best = rows[-1]
    return {"best": best, "curve": pd.DataFrame(rows),
            "default_value": float(
                gain_tp * int(((p >= 0.5) & (y == 1)).sum())
                - cost_fp * int(((p >= 0.5) & (y == 0)).sum())
                - cost_fn * int(((p < 0.5) & (y == 1)).sum())),
            "note": "порог 0.5 — это не значение по умолчанию, а произвольный "
                    "выбор, который почти никогда не оптимален"}


def regression_metrics(y_true, y_pred):
    """MAE, RMSE, MAPE, R² и когда какая обманывает."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    err = p - y
    rmse = float(np.sqrt(np.mean(err ** 2)))
    mae = float(mean_absolute_error(y, p))
    nz = y != 0
    mape = float(np.mean(np.abs(err[nz] / y[nz])) * 100) if nz.any() else None
    return {"mae": mae, "rmse": rmse, "mape": mape,
            "r2": float(r2_score(y, p)),
            "rmse_to_mae": rmse / mae if mae else None,
            "note": "RMSE заметно выше MAE — в ошибках есть крупные выбросы; "
                    "MAPE не считается по нулевым значениям и взрывается "
                    "рядом с нулём"}


# --- пайплайн --------------------------------------------------------------

def build_pipeline(cat_cols, num_cols, model, scale=True):
    """Сборка ColumnTransformer и Pipeline.

    Весь препроцессинг внутри пайплайна — единственный способ, при котором
    кросс-валидация не подсматривает в тестовый фолд.
    """
    num_steps = [("imp", SimpleImputer(strategy="median"))]
    if scale:
        num_steps.append(("sc", StandardScaler()))
    pre = ColumnTransformer([
        ("cat", Pipeline([
            ("imp", SimpleImputer(strategy="most_frequent")),
            ("oh", OneHotEncoder(handle_unknown="ignore"))]), list(cat_cols)),
        ("num", Pipeline(num_steps), list(num_cols)),
    ])
    return Pipeline([("pre", pre), ("model", model)])


def learning_curve_verdict(train_scores, val_scores, gap_threshold=0.1,
                           low_threshold=0.7):
    """Диагноз по качеству на обучении и на валидации."""
    tr = float(np.mean(train_scores))
    va = float(np.mean(val_scores))
    gap = tr - va
    if gap >= gap_threshold and tr > low_threshold:
        verdict = "переобучение"
        advice = ("больше данных, регуляризация, меньше признаков, "
                  "проще модель")
    elif tr < low_threshold and va < low_threshold:
        verdict = "недообучение"
        advice = "сложнее модель, больше признаков, меньше регуляризации"
    else:
        verdict = "приемлемо"
        advice = ""
    return {"train": tr, "val": va, "gap": gap, "verdict": verdict,
            "advice": advice}


def cv_score(pipeline, X, y, cv=5, scoring="roc_auc", seed=0):
    """Кросс-валидация со стратификацией и интервалом разброса."""
    skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=seed)
    scores = cross_val_score(pipeline, X, y, cv=skf, scoring=scoring)
    mean, std = float(scores.mean()), float(scores.std())
    return {"scores": [float(s) for s in scores], "mean": mean, "std": std,
            "lo": mean - 2 * std, "hi": mean + 2 * std,
            "stable": bool(std < 0.05),
            "note": "разброс между фолдами говорит, насколько числу можно "
                    "верить: 0.85 ± 0.10 и 0.85 ± 0.01 — разные результаты"}
