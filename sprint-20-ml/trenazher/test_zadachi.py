"""
Проверка решений тренажёра спринта 20.

Запуск:      make test SPRINT=20
Одна задача: python3 -m pytest sprint-20-ml/trenazher -q -k leak
"""

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

import zadachi as z

RNG = np.random.default_rng(0)
Y = np.array([0] * 75 + [1] * 25)


# --- 1. целевая переменная -------------------------------------------------

USERS = pd.DataFrame({"user_id": [1, 2, 3, 4],
                      "reg_date": ["2026-01-01", "2026-01-10", "2026-02-01",
                                   "2026-02-20"]})
EVENTS = pd.DataFrame({
    "user_id": [1, 1, 2, 3],
    "event": ["deposit", "view", "deposit", "view"],
    "ts": ["2026-01-05", "2026-01-02", "2026-03-01", "2026-02-02"]})


def test_define_target():
    out = z.define_target(EVENTS, USERS, window_days=30)
    assert out["n"] == 4 and out["positives"] == 1
    assert list(out["table"]["y"]) == [1, 0, 0, 0], \
        "у второго депозит был через 50 дней — вне окна"
    assert out["window_days"] == 30
    assert "30" in out["definition"]


def test_define_target_window_matters():
    wide = z.define_target(EVENTS, USERS, window_days=60)
    assert wide["positives"] == 2, \
        ("то же событие, другое окно — другая целевая переменная. "
         "Поэтому окно входит в определение, а не подразумевается")


# --- 2. окно наблюдения ----------------------------------------------------

def test_check_observation_window():
    out = z.check_observation_window(USERS, "2026-02-25", window_days=30)
    assert out["cutoff"] == pd.Timestamp("2026-01-26")
    assert out["incomplete"] == 2 and out["usable"] == 2
    assert out["share_incomplete"] == pytest.approx(0.5)


def test_check_observation_window_all_complete():
    out = z.check_observation_window(USERS, "2026-12-31", window_days=30)
    assert out["incomplete"] == 0 and out["usable"] == 4


# --- 3. baseline -----------------------------------------------------------

def test_baseline_scores():
    rule = np.array([0] * 70 + [1] * 5 + [0] * 5 + [1] * 20)
    out = z.baseline_scores(Y, rule)
    assert out["positive_rate"] == pytest.approx(0.25)
    assert out["constant"]["roc_auc"] == 0.5
    assert out["constant"]["accuracy_all_zero"] == pytest.approx(0.75), \
        "болван, всегда отвечающий «нет», получает accuracy 75%"
    assert out["rule"]["roc_auc"] == pytest.approx(0.8667, abs=1e-3)
    assert out["rule"]["recall"] == pytest.approx(0.8)


def test_baseline_without_rule():
    out = z.baseline_scores(Y)
    assert "rule" not in out
    assert out["constant"]["pr_auc"] == pytest.approx(0.25, abs=1e-6)


# --- 4. поиск утечки -------------------------------------------------------

DF_LEAK = pd.DataFrame({
    "y": Y,
    "good": RNG.normal(0, 1, 100) + Y * 0.6,
    "leaky": Y * 1.0 + RNG.normal(0, 0.01, 100),
    "is_verified": Y,
    "const": np.ones(100),
    "noise": RNG.normal(0, 1, 100)})


def test_leak_scan_finds_obvious():
    out = z.leak_scan(DF_LEAK, "y")
    assert "leaky" in out["suspicious"]
    assert "noise" not in out["suspicious"] and "good" not in out["suspicious"]
    assert out["clean"] is False


def test_leak_scan_flags_state_columns():
    out = z.leak_scan(DF_LEAK, "y")
    assert "is_verified" in out["suspicious"], \
        ("признак-состояние без отметки времени: в обучении он есть, "
         "а в момент прогноза его значение неизвестно")


def test_leak_scan_skips_constants_and_clean_data():
    out = z.leak_scan(DF_LEAK, "y")
    assert "const" not in out["suspicious"]
    clean = pd.DataFrame({"y": Y, "a": RNG.normal(0, 1, 100),
                          "b": RNG.normal(0, 1, 100)})
    assert z.leak_scan(clean, "y")["clean"] is True


# --- 5-6. разделение -------------------------------------------------------

TIMED = pd.DataFrame({"id": range(100),
                      "t": pd.date_range("2026-01-01", periods=100),
                      "y": RNG.integers(0, 2, 100)})


def test_time_split():
    out = z.time_split(TIMED, "t")
    assert out["n_train"] == 75 and out["n_test"] == 25
    assert out["train"]["t"].max() < out["test"]["t"].min(), \
        "в train не должно быть ничего позже начала test"
    assert out["boundary"] == out["test"]["t"].min()


def test_split_sanity_ok():
    out = z.time_split(TIMED, "t")
    s = z.split_sanity(out["train"], out["test"], "id", "y", "t")
    assert s["overlap"] == 0 and s["time_leak"] is False


def test_split_sanity_catches_overlap():
    tr = TIMED.iloc[:60]
    te = TIMED.iloc[50:]
    s = z.split_sanity(tr, te, "id", "y")
    assert s["overlap"] == 10 and s["ok"] is False
    assert any("train" in p and "test" in p for p in s["problems"])


def test_split_sanity_catches_time_leak():
    shuffled = TIMED.sample(frac=1, random_state=1)
    tr, te = shuffled.iloc[:75], shuffled.iloc[75:]
    s = z.split_sanity(tr, te, "id", "y", "t")
    assert s["time_leak"] is True, \
        "случайное разделение по времени — утечка из будущего"


def test_split_sanity_catches_single_class_test():
    tr = pd.DataFrame({"id": [1, 2], "y": [0, 1]})
    te = pd.DataFrame({"id": [3, 4], "y": [0, 0]})
    s = z.split_sanity(tr, te, "id", "y")
    assert any("один класс" in p for p in s["problems"])


# --- 7-8. кодирование ------------------------------------------------------

def test_encode_categorical_label_and_onehot():
    oh = z.encode_categorical(["a", "b", "a", "c"], "onehot")
    assert oh["n_columns"] == 3 and oh["warning"] == ""
    lb = z.encode_categorical(["a", "b", "a", "c"], "label")
    assert lb["codes"] == [0, 1, 0, 2]
    assert lb["mapping"] == {"a": 0, "b": 1, "c": 2}
    assert "порядок" in lb["warning"]


def test_encode_categorical_target_warns_about_leak():
    tg = z.encode_categorical(["a", "b", "a", "b"], "target", target=[1, 0, 1, 0])
    assert tg["codes"] == [1.0, 0.0, 1.0, 0.0]
    assert "утечк" in tg["warning"].lower()
    with pytest.raises(ValueError):
        z.encode_categorical(["a"], "target")
    with pytest.raises(ValueError):
        z.encode_categorical(["a"], "hashing")


def test_encode_categorical_onehot_warns_on_high_cardinality():
    many = z.encode_categorical([f"c{i}" for i in range(30)], "onehot")
    assert many["n_columns"] == 30 and many["warning"] != ""


def test_target_encoding_leak():
    cat = ["a"] * 20 + ["b"] * 20 + ["c"] * 10
    tgt = [1] * 15 + [0] * 5 + [0] * 18 + [1] * 2 + [1] * 5 + [0] * 5
    out = z.target_encoding_leak(cat, tgt)
    assert out["auc_naive"] > out["auc_out_of_fold"], \
        "кодировка по всей выборке подсматривает в целевую переменную"
    assert out["inflation"] > 0
    assert out["leaks"] is True


# --- 9-10. масштаб и пропуски ----------------------------------------------

@pytest.mark.parametrize("model,expected", [
    ("logreg", True), ("knn", True), ("kmeans", True), ("svm", True),
    ("random_forest", False), ("gradient_boosting", False), ("tree", False)])
def test_needs_scaling(model, expected):
    assert z.needs_scaling(model)["needs_scaling"] is expected


def test_needs_scaling_unknown():
    with pytest.raises(ValueError):
        z.needs_scaling("prophet")


def test_missing_strategy():
    none = z.missing_strategy([1, 2, 3], "x")
    assert none["strategy"] == "ничего" and none["add_flag"] is False
    num = z.missing_strategy([1, 2, None, 4], "age")
    assert num["missing_share"] == pytest.approx(0.25)
    assert "медиан" in num["strategy"] and num["add_flag"] is True
    drop = z.missing_strategy([None] * 7 + [1, 2, 3], "sparse")
    assert drop["strategy"] == "выбросить признак"
    cat = z.missing_strategy(["a", None, "b", "c"], "city")
    assert "категория" in cat["strategy"]


# --- 11-12. метрики классификации ------------------------------------------

PROBA = np.clip(Y * 0.6 + RNG.normal(0, 0.2, 100) + 0.2, 0, 1)


def test_classification_metrics():
    out = z.classification_metrics(Y, PROBA)
    assert out["tp"] + out["fn"] == 25 and out["fp"] + out["tn"] == 75
    assert out["threshold"] == 0.5
    assert 0 <= out["precision"] <= 1 and 0 <= out["recall"] <= 1
    assert out["roc_auc"] > 0.9


def test_classification_metrics_threshold_moves_the_tradeoff():
    low = z.classification_metrics(Y, PROBA, threshold=0.2)
    high = z.classification_metrics(Y, PROBA, threshold=0.8)
    assert low["recall"] >= high["recall"]
    assert low["fp"] >= high["fp"], \
        "ниже порог — больше находим и больше ошибаемся"


def test_accuracy_trap():
    out = z.accuracy_trap(Y, np.full(100, 0.1))
    assert out["model_accuracy"] == pytest.approx(0.75)
    assert out["always_zero_accuracy"] == pytest.approx(0.75)
    assert out["beats_dumb"] is False
    assert out["recall"] == pytest.approx(0.0), \
        ("accuracy 75% при нулевом recall: модель не нашла ни одного "
         "целевого объекта, а в отчёте выглядит прилично")


# --- 13. порог под бизнес --------------------------------------------------

def test_threshold_for_business_moves_off_half():
    rng = np.random.default_rng(7)
    y = np.array([0] * 800 + [1] * 200)
    p = np.clip(0.25 + y * 0.25 + rng.normal(0, 0.18, 1000), 0, 1)
    out = z.threshold_for_business(y, p, cost_fp=1, cost_fn=20)
    assert out["best"]["threshold"] < 0.5, \
        ("пропустить целевого в двадцать раз дороже лишнего контакта — "
         "порог обязан уехать вниз")
    assert out["best"]["value"] > out["default_value"]
    assert len(out["curve"]) == 101


def test_threshold_for_business_expensive_contact():
    rng = np.random.default_rng(7)
    y = np.array([0] * 800 + [1] * 200)
    p = np.clip(0.25 + y * 0.25 + rng.normal(0, 0.18, 1000), 0, 1)
    out = z.threshold_for_business(y, p, cost_fp=20, cost_fn=1)
    assert out["best"]["threshold"] > 0.5, \
        "дорогой контакт — зовём только тех, в ком уверены"


# --- 14. метрики регрессии -------------------------------------------------

def test_regression_metrics():
    out = z.regression_metrics([10, 20, 30, 40], [12, 19, 33, 60])
    assert out["mae"] == pytest.approx(6.5)
    assert out["rmse"] == pytest.approx(10.1735, abs=1e-3)
    assert out["mape"] == pytest.approx(21.25, abs=0.01)
    assert out["rmse_to_mae"] > 1.5, \
        "RMSE заметно выше MAE — в ошибках есть крупный промах"


def test_regression_metrics_mape_needs_nonzero():
    out = z.regression_metrics([0, 0], [1, 2])
    assert out["mape"] is None, "MAPE не считается по нулевым значениям"


# --- 15-17. пайплайн и валидация -------------------------------------------

X = pd.DataFrame({"c": ["a", "b"] * 50,
                  "n": RNG.normal(0, 1, 100) + Y})


def test_build_pipeline_structure():
    pipe = z.build_pipeline(["c"], ["n"], LogisticRegression(max_iter=500))
    assert [name for name, _ in pipe.steps] == ["pre", "model"]
    pipe.fit(X, Y)
    assert pipe.predict_proba(X).shape == (100, 2)


def test_build_pipeline_survives_unseen_category():
    pipe = z.build_pipeline(["c"], ["n"], LogisticRegression(max_iter=500))
    pipe.fit(X, Y)
    unseen = pd.DataFrame({"c": ["zzz"], "n": [0.0]})
    assert pipe.predict(unseen).shape == (1,), \
        ("handle_unknown='ignore': в проде обязательно встретится "
         "категория, которой не было в обучении")


def test_learning_curve_verdict():
    over = z.learning_curve_verdict([0.95], [0.72])
    assert over["verdict"] == "переобучение" and over["advice"]
    under = z.learning_curve_verdict([0.60], [0.58])
    assert under["verdict"] == "недообучение"
    ok = z.learning_curve_verdict([0.86], [0.84])
    assert ok["verdict"] == "приемлемо" and ok["advice"] == ""


def test_cv_score():
    pipe = z.build_pipeline(["c"], ["n"], LogisticRegression(max_iter=500))
    out = z.cv_score(pipe, X, Y, cv=5)
    assert len(out["scores"]) == 5
    assert out["lo"] == pytest.approx(out["mean"] - 2 * out["std"])
    assert 0 <= out["mean"] <= 1
    assert isinstance(out["stable"], bool)
