"""
Проверка решений тренажёра спринта 21.

Запуск:      make test SPRINT=21
Одна задача: python3 -m pytest sprint-21-modeli/trenazher -q -k cluster
"""

import numpy as np
import pandas as pd
import pytest
from sklearn.cluster import KMeans
from sklearn.linear_model import LogisticRegression

import zadachi as z

RNG = np.random.default_rng(0)
Y_IMBALANCED = np.array([0] * 950 + [1] * 50)


# --- 1. выбор модели -------------------------------------------------------

def test_choose_model_family():
    assert "бустинг" in z.choose_model_family(200_000, 30)["family"]
    assert "логистическая" in z.choose_model_family(500, 5)["family"]
    assert "лес" in z.choose_model_family(20_000, 10)["family"]


def test_choose_model_family_interpretability_wins():
    out = z.choose_model_family(500_000, 80, need_interpretable=True)
    assert "логистическая" in out["family"] and out["interpretable"] is True, \
        ("интерпретируемость — требование заказчика, а не параметр данных: "
         "модель, решение которой нельзя объяснить, не внедрят")
    assert out["caveat"]


# --- 2-3. дисбаланс --------------------------------------------------------

def test_class_imbalance():
    out = z.class_imbalance(Y_IMBALANCED)
    assert out["positive_rate"] == pytest.approx(0.05)
    assert out["minority_rate"] == pytest.approx(0.05)
    assert out["ratio"] == pytest.approx(19.0)
    assert out["severe"] is True
    assert z.class_imbalance([]) is None


def test_class_imbalance_works_in_reverse():
    """В задаче оттока меньшинство — это остающиеся."""
    y = np.array([1] * 644 + [0] * 356)
    out = z.class_imbalance(y)
    assert out["positive_rate"] == pytest.approx(0.644)
    assert out["minority_rate"] == pytest.approx(0.356)
    assert out["severe"] is False


def test_resample_plan():
    cw = z.resample_plan(Y_IMBALANCED, "class_weight")
    assert cw["keeps_all_data"] is True
    assert cw["weights"][1] == pytest.approx(10.0)
    assert cw["weights"][0] == pytest.approx(1000 / (2 * 950))
    under = z.resample_plan(Y_IMBALANCED, "undersample")
    assert under["rows_after"] == 100 and under["rows_dropped"] == 900
    assert under["keeps_all_data"] is False and under["warning"]
    over = z.resample_plan(Y_IMBALANCED, "oversample")
    assert over["rows_after"] == 1900 and over["rows_added"] == 900
    assert "фолд" in over["warning"], \
        "oversample делают только внутри обучающего фолда"
    with pytest.raises(ValueError):
        z.resample_plan(Y_IMBALANCED, "smote")


# --- 4. определение оттока -------------------------------------------------

ACT = pd.DataFrame({
    "user_id": [1, 1, 2, 3, 3],
    "ts": ["2026-01-01", "2026-05-10", "2026-01-05", "2026-01-02", "2026-03-01"]})


def test_define_churn():
    out = z.define_churn(ACT, "2026-04-30", 60)
    assert out["n"] == 3, "в выборку идут только активные до отсечки"
    assert out["churned"] == 2
    t = out["table"].set_index("user_id")
    assert t.loc[1, "churned"] == 0, "вернулся 10 мая — в окне наблюдения"
    assert t.loc[2, "churned"] == 1 and t.loc[3, "churned"] == 1
    assert out["horizon_end"] == pd.Timestamp("2026-06-29")


def test_define_churn_horizon_changes_the_task():
    short = z.define_churn(ACT, "2026-04-30", 5)
    assert short["churned"] == 3, \
        ("тот же клиент при горизонте 5 дней считается ушедшим, при 60 — нет. "
         "Отток — определение аналитика, а не свойство пользователя")


def test_define_churn_min_history():
    out = z.define_churn(ACT, "2026-04-30", 60, min_history_days=118)
    assert out["n"] == 2, \
        "у второго история 115 дней — короче требуемых 118, он исключён"
    assert 2 not in set(out["table"]["user_id"])


# --- 5. RFM ----------------------------------------------------------------

ORDERS = pd.DataFrame({
    "user_id": [1, 1, 2, 1],
    "ts": ["2026-01-01", "2026-03-01", "2026-02-01", "2026-06-01"],
    "amount": [100.0, 50.0, 30.0, 999.0]})


def test_rfm_features():
    out = z.rfm_features(ORDERS, "2026-04-30").set_index("user_id")
    assert out.loc[1, "frequency"] == 2, "заказ от 1 июня — после отсечки"
    assert out.loc[1, "monetary"] == pytest.approx(150.0)
    assert out.loc[1, "recency_days"] == 60
    assert out.loc[1, "tenure_days"] == 119
    assert out.loc[1, "avg_check"] == pytest.approx(75.0)
    assert out.loc[2, "frequency"] == 1


# --- 6-7. деньги удержания -------------------------------------------------

def test_retention_value():
    high = z.retention_value(0.8, ltv=200, retention_cost=20)
    assert high["expected_gain"] == pytest.approx(48.0)
    assert high["value"] == pytest.approx(28.0) and high["worth_it"] is True
    low = z.retention_value(0.1, ltv=200, retention_cost=20)
    assert low["worth_it"] is False
    assert high["breakeven_prob"] == pytest.approx(1 / 3), \
        "ниже трети вероятности удерживать невыгодно при этих ценах"


def test_retention_value_success_rate_matters():
    good_model = z.retention_value(0.9, ltv=200, retention_cost=20,
                                   success_rate=0.05)
    worse_model = z.retention_value(0.7, ltv=200, retention_cost=20,
                                    success_rate=0.40)
    assert worse_model["value"] > good_model["value"], \
        ("модель хуже, а денег больше: качество удержания важнее качества "
         "прогноза")


def test_churn_threshold_beats_default():
    rng = np.random.default_rng(0)
    y = np.array([0] * 700 + [1] * 300)
    p = np.clip(0.3 + y * 0.3 + rng.normal(0, 0.15, 1000), 0, 1)
    out = z.churn_threshold(y, p, ltv=200, retention_cost=20)
    assert len(out["curve"]) == 101
    assert out["best"]["value"] >= out["value_at_half"]
    assert set(out["curve"].columns) == {"threshold", "targeted",
                                         "true_churners", "value"}


# --- 8. интерпретация логрега ----------------------------------------------

def test_logreg_interpret():
    out = z.logreg_interpret(["recency", "orders"], [0.7, -1.2])
    top = out["top"]
    assert top[0]["feature"] == "orders", "сортировка по модулю коэффициента"
    assert top[0]["direction"] == "снижает риск"
    assert top[0]["odds_ratio"] == pytest.approx(np.exp(-1.2))
    rec = [r for r in out["all"] if r["feature"] == "recency"][0]
    assert rec["effect_pct"] == pytest.approx((np.exp(0.7) - 1) * 100)
    assert "масштаб" in out["note"]


# --- 9-10. важность признаков ----------------------------------------------

def test_importance_caveats():
    out = z.importance_caveats([0.5, 0.3, 0.2], ["user_id", "x", "y"],
                               cardinalities={"user_id": 1000, "x": 3, "y": 4},
                               correlated_groups=[{"x", "y"}])
    assert out["ranking"][0]["feature"] == "user_id"
    assert out["sums_to_one"] is True
    assert len(out["warnings"]) == 2
    assert any("user_id" in w for w in out["warnings"])
    assert "permutation" in out["advice"] or "SHAP" in out["advice"]


def test_permutation_importance_manual():
    rng = np.random.default_rng(1)
    y = np.array([0] * 500 + [1] * 500)
    X = pd.DataFrame({"signal": rng.normal(0, 1, 1000) + y * 1.5,
                      "noise": rng.normal(0, 1, 1000)})
    m = LogisticRegression(max_iter=500).fit(X, y)
    sig = z.permutation_importance_manual(m, X, y, "signal")
    noi = z.permutation_importance_manual(m, X, y, "noise")
    assert sig["matters"] is True and noi["matters"] is False
    assert sig["mean_drop"] > noi["mean_drop"]
    assert 0 < sig["baseline_auc"] <= 1


# --- 11. объяснение прогноза -----------------------------------------------

def test_explain_prediction():
    out = z.explain_prediction({"recency": 90, "orders": 1},
                               {"recency": 0.3, "orders": 0.2}, base_rate=0.3)
    assert out["prediction"] == pytest.approx(0.8)
    assert out["top_factors"][0]["feature"] == "recency"
    assert "recency = 90 повышает риск" in out["text"]
    assert z.explain_prediction({}, {}, 0.4)["text"] == "значимых факторов нет"


# --- 12-13. регрессия ------------------------------------------------------

def test_residual_analysis_detects_heteroscedasticity():
    rng = np.random.default_rng(2)
    y = np.arange(1, 201, dtype=float)
    pred = y + rng.normal(0, 1, 200) * y / 20
    out = z.residual_analysis(y, pred)
    assert out["ok"] is False
    assert any("разброс" in p for p in out["problems"])


def test_residual_analysis_clean():
    rng = np.random.default_rng(3)
    y = rng.normal(100, 20, 500)
    pred = y + rng.normal(0, 1, 500)
    out = z.residual_analysis(y, pred)
    assert out["problems"] == [] and out["ok"] is True


def test_vif_check():
    rng = np.random.default_rng(4)
    d = pd.DataFrame({"x": rng.normal(0, 1, 300)})
    d["y"] = d["x"] * 2 + rng.normal(0, 0.01, 300)
    d["z"] = rng.normal(0, 1, 300)
    out = z.vif_check(d)
    assert set(out["problematic"]) == {"x", "y"}
    assert out["ok"] is False
    assert out["table"][0]["vif"] > out["table"][-1]["vif"]
    assert "прогноз" in out["note"].lower(), \
        "мультиколлинеарность портит коэффициенты, а не качество прогноза"


# --- 14-15. подготовка и число кластеров -----------------------------------

RFM = pd.DataFrame({"recency_days": RNG.integers(1, 200, 400),
                    "frequency": RNG.integers(1, 30, 400),
                    "monetary": RNG.lognormal(4, 1, 400)})


def test_scale_for_clustering():
    out = z.scale_for_clustering(RFM, ["recency_days", "frequency", "monetary"],
                                 log_columns=["monetary"])
    assert out["array"].shape == (400, 3)
    assert out["logged"] == ["monetary"]
    assert abs(out["array"].mean()) < 1e-9, "после масштабирования среднее ноль"
    assert out["array"][:, 2].max() < 10, \
        "логарифм прижал хвост денег: без него кластеры соберутся вокруг выбросов"


def test_elbow_and_silhouette():
    X = z.scale_for_clustering(RFM, ["recency_days", "frequency", "monetary"],
                               log_columns=["monetary"])["array"]
    out = z.elbow_and_silhouette(X, k_range=(2, 6))
    t = out["table"]
    assert list(t["k"]) == [2, 3, 4, 5]
    assert t["inertia"].is_monotonic_decreasing, \
        "инерция всегда падает с ростом k — поэтому по ней одной k не выбирают"
    assert out["best_by_silhouette"] in [2, 3, 4, 5]
    assert "бизнес" in out["note"]


# --- 16-17. описание и именование ------------------------------------------

def test_describe_clusters():
    X = z.scale_for_clustering(RFM, ["recency_days", "frequency", "monetary"],
                               log_columns=["monetary"])["array"]
    labels = KMeans(n_clusters=3, random_state=42, n_init=10).fit_predict(X)
    prof = z.describe_clusters(RFM, labels, ["recency_days", "frequency"])
    assert len(prof) == 3
    assert set(["cluster", "size", "share", "recency_days", "frequency"]) <= set(prof.columns)
    assert prof["size"].sum() == 400
    assert prof["share"].sum() == pytest.approx(1.0)


def test_name_clusters_all_named():
    prof = pd.DataFrame({"cluster": [0, 1], "size": [100, 50],
                         "frequency": [25, 2], "recency_days": [5, 150]})
    rules = [("чемпионы", lambda r: r["frequency"] > 20),
             ("спящие", lambda r: r["recency_days"] > 120)]
    out = z.name_clusters(prof, rules)
    assert out["all_named"] is True
    assert {e["name"] for e in out["named"]} == {"чемпионы", "спящие"}


def test_name_clusters_unnamed_is_a_signal():
    prof = pd.DataFrame({"cluster": [0, 1], "size": [100, 50],
                         "frequency": [3, 4], "recency_days": [40, 50]})
    rules = [("чемпионы", lambda r: r["frequency"] > 20)]
    out = z.name_clusters(prof, rules)
    assert out["all_named"] is False and len(out["unnamed"]) == 2
    assert "бесполезн" in out["verdict"], \
        "кластер, который нельзя описать словами, бизнес использовать не сможет"


def test_rfm_segments():
    out = z.rfm_segments(RFM)
    t = out["table"]
    assert set(["R", "F", "M", "rfm", "score", "segment"]) <= set(t.columns)
    assert t["R"].between(1, 3).all() and t["score"].between(3, 9).all()
    assert sum(out["counts"].values()) == 400
    assert "RFM" in out["note"] or "кластериз" in out["note"]


# --- 18. дрейф -------------------------------------------------------------

def test_psi_stable():
    rng = np.random.default_rng(5)
    out = z.psi(rng.normal(0, 1, 2000), rng.normal(0, 1, 2000))
    assert out["psi"] < 0.1 and out["verdict"] == "стабильно"
    assert out["action"] == ""


def test_psi_detects_drift():
    rng = np.random.default_rng(5)
    out = z.psi(rng.normal(0, 1, 2000), rng.normal(2, 1, 2000))
    assert out["psi"] > 0.25 and out["verdict"] == "сильный сдвиг"
    assert "переобучить" in out["action"]


def test_psi_needs_variation():
    assert z.psi([1.0] * 100, [1.0] * 100) is None, \
        "на константе корзины не построить"
