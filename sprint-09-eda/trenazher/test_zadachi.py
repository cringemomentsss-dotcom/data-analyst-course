"""
Проверка решений тренажёра спринта 9.

Запуск:      make test SPRINT=09
Одна задача: python3 -m pytest sprint-09-eda/trenazher -q -k corr_pairs
"""

import numpy as np
import pandas as pd
import pytest

import zadachi as z

DF = pd.DataFrame({
    "bill":   [300.0, 500.0, 700.0, 900.0, 1100.0, 1300.0, 9000.0, np.nan],
    "seats":  [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 500.0, 25.0],
    "rating": [3.5, 3.8, 4.0, 4.2, 4.4, 4.6, 4.9, 4.1],
    "cat":    ["кафе", "кафе", "бар", "бар", "бар", "ресторан", "ресторан", None],
})


# --- 1. describe_numeric ---------------------------------------------------

def test_describe_numeric():
    out = z.describe_numeric(DF, ["bill", "seats"])
    assert list(out.index) == ["bill", "seats"]
    for col in ["count", "missing", "mean", "median", "std",
                "min", "p25", "p75", "max", "iqr"]:
        assert col in out.columns, f"нет столбца {col}"
    assert out.loc["bill", "count"] == 7
    assert out.loc["bill", "missing"] == 1
    assert out.loc["bill", "median"] == pytest.approx(900.0)
    assert out.loc["bill", "iqr"] == pytest.approx(
        DF["bill"].quantile(0.75) - DF["bill"].quantile(0.25))


# --- 2. outlier_bounds_iqr -------------------------------------------------

def test_outlier_bounds_iqr():
    lo, hi = z.outlier_bounds_iqr(DF["bill"])
    q1, q3 = DF["bill"].quantile(0.25), DF["bill"].quantile(0.75)
    assert lo == pytest.approx(q1 - 1.5 * (q3 - q1))
    assert hi == pytest.approx(q3 + 1.5 * (q3 - q1))
    assert DF["bill"].max() > hi, "9000 должен оказаться выбросом"


# --- 3. clip_outliers ------------------------------------------------------

def test_clip_outliers():
    out = z.clip_outliers(DF["bill"], 400, 1200)
    assert out.min() == 400.0
    assert out.max() == 1200.0
    assert pd.isna(out.iloc[-1]), "пропуск остаётся пропуском, а не границей"
    assert len(out) == len(DF), "clip не удаляет строки"


# --- 4. correlation_matrix -------------------------------------------------

def test_correlation_matrix():
    m = z.correlation_matrix(DF, ["bill", "seats", "rating"])
    assert m.shape == (3, 3)
    assert m.loc["bill", "bill"] == pytest.approx(1.0)
    assert m.loc["bill", "seats"] == pytest.approx(m.loc["seats", "bill"])
    sp = z.correlation_matrix(DF, ["bill", "rating"], method="spearman")
    assert sp.loc["bill", "rating"] == pytest.approx(1.0), \
        "по рангам связь монотонная и полная"


# --- 5. corr_pairs ---------------------------------------------------------

def test_corr_pairs():
    out = z.corr_pairs(DF, ["bill", "seats", "rating"], threshold=0.3)
    assert list(out.columns) == ["x", "y", "corr"]
    assert len(out) >= 1
    vals = out["corr"].abs().tolist()
    assert vals == sorted(vals, reverse=True), "сортировка по модулю, по убыванию"
    assert not ((out["x"] == out["y"]).any()), "пара столбца с самим собой не нужна"
    empty = z.corr_pairs(DF, ["bill", "rating"], threshold=0.999999)
    assert len(empty) == 0
    assert list(empty.columns) == ["x", "y", "corr"], \
        "пустой результат всё равно должен иметь столбцы"


# --- 6. compare_methods ----------------------------------------------------

def test_compare_methods():
    out = z.compare_methods(DF, "bill", "rating")
    assert set(out) == {"pearson", "spearman"}
    assert out["spearman"] == pytest.approx(1.0)
    assert out["spearman"] > out["pearson"], \
        "выброс тянет Пирсона вниз, Спирмен его игнорирует — в этом весь смысл"


# --- 7. histogram_counts ---------------------------------------------------

def test_histogram_counts():
    counts, edges = z.histogram_counts(DF["bill"], 4)
    assert len(counts) == 4 and len(edges) == 5
    assert sum(counts) == 7, "пропуск в гистограмму не попадает"
    assert edges[0] == pytest.approx(300.0)
    assert edges[-1] == pytest.approx(9000.0)


# --- 8. filter_valid -------------------------------------------------------

def test_filter_valid():
    out, report = z.filter_valid(DF, {"bill": (100, 2000), "seats": (5, 100)})
    assert len(out) == 6, "остаться должны только строки, прошедшие оба правила"
    assert report.loc["bill", "missing"] == 1
    assert report.loc["bill", "out_of_range"] == 1
    assert report.loc["seats", "out_of_range"] == 1
    assert "missing" in report.columns and "out_of_range" in report.columns, \
        "пропуски и выход за диапазон надо считать ОТДЕЛЬНО: это разные причины потери строк"


# --- 9. group_compare ------------------------------------------------------

def test_group_compare():
    out = z.group_compare(DF, "cat", "bill")
    assert list(out.columns) == ["count", "mean", "median", "std"]
    assert out.loc["кафе", "count"] == 2
    assert out.loc["кафе", "median"] == pytest.approx(400.0)
    assert out.index[0] == "ресторан", "сортировка по убыванию медианы"
    assert out["count"].sum() == 7, "группа с пропущенным ключом не выбрасывается"


# --- 10. bin_stats ---------------------------------------------------------

def test_bin_stats():
    out = z.bin_stats(DF, "bill", [600, 1200], ["низкий", "средний", "высокий"], "rating")
    assert list(out.index.astype(str)) == ["низкий", "средний", "высокий"]
    assert list(out.columns) == ["count", "mean", "median"]
    assert out.loc["низкий", "count"] == 2
    assert out.loc["высокий", "count"] == 2
    assert out.loc["высокий", "mean"] > out.loc["низкий", "mean"]


# --- 11. share_matrix ------------------------------------------------------

def test_share_matrix():
    df = pd.DataFrame({
        "okrug": ["ЦАО", "ЦАО", "ЮАО", "ЮАО"],
        "cat": ["кафе", "бар", "кафе", "кафе"],
        "n": [30.0, 70.0, 5.0, 5.0],
    })
    out = z.share_matrix(df, "okrug", "cat", "n")
    assert out.loc["ЦАО", "кафе"] == pytest.approx(30.0)
    assert out.loc["ЦАО", "бар"] == pytest.approx(70.0)
    assert out.loc["ЮАО", "кафе"] == pytest.approx(100.0)
    assert out.loc["ЮАО", "бар"] == pytest.approx(0.0)
    assert out.sum(axis=1).round(1).tolist() == [100.0, 100.0], \
        "каждая строка должна давать 100%"


# --- 12. top_bottom --------------------------------------------------------

def test_top_bottom():
    top, bottom = z.top_bottom(DF, "cat", "bill", 2)
    assert len(top) == 2 and len(bottom) == 2
    assert top.index[0] == "ресторан"
    # Группа с незаполненной категорией не выбрасывается — и потому оказывается
    # в самом низу: единственная её строка не имеет чека, сумма нулевая.
    # Это не баг, а то, что аналитик обязан заметить и объяснить в отчёте.
    assert bottom.index.isna().any(), \
        "группу с пропущенным ключом выбрасывать нельзя, она должна быть видна"
    assert "кафе" in bottom.index

    clean = DF.dropna(subset=["cat"])
    top2, bottom2 = z.top_bottom(clean, "cat", "bill", 1)
    assert top2.index[0] == "ресторан"
    assert bottom2.index[0] == "кафе"


# --- 13. plot_hist ---------------------------------------------------------

def test_plot_hist():
    ax = z.plot_hist(DF["bill"], bins=5)
    assert len(ax.patches) == 5, "должно быть по прямоугольнику на корзину"
    assert ax.get_ylabel(), "ось Y обязана быть подписана"
    assert ax.get_xlabel(), "ось X обязана быть подписана"


# --- 14. plot_group_bars ---------------------------------------------------

def test_plot_group_bars():
    ax = z.plot_group_bars(DF, "cat", "bill")
    assert len(ax.patches) == 4, "три категории плюс группа с пропущенным ключом"
    assert ax.get_xlabel() and ax.get_ylabel()
