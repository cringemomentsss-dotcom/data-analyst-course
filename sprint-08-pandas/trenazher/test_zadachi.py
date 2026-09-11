"""
Проверка решений тренажёра спринта 8.

Запуск:      make test SPRINT=08
Одна задача: python3 -m pytest sprint-08-pandas/trenazher -q -k to_number
"""

import os

import numpy as np
import pandas as pd
import pytest

import zadachi as z

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixture.csv")


# --- 1. load_csv -----------------------------------------------------------

def test_load_csv():
    df = z.load_csv(FIXTURE)
    assert len(df) == 12
    assert list(df.columns) == ["player_id", "reg_date", "country", "platform",
                                "price", "sessions"]
    assert df["price"].dtype == object or str(df["price"].dtype) == "str", \
        "читать надо как строки: dtype=str, иначе pandas сам испортит грязные значения"
    assert df.loc[0, "country"] == "DE"
    assert df.loc[4, "country"] == "", \
        "keep_default_na=False: пустое поле должно остаться пустой строкой, а не NaN"


# --- 2. to_missing ---------------------------------------------------------

def test_to_missing():
    s = pd.Series(["a", "", "null", "-", "н/д", "NaN", "b", " "])
    out = z.to_missing(s)
    assert out.isna().sum() == 6
    assert out.iloc[0] == "a"
    assert out.iloc[6] == "b"


# --- 3. to_number ----------------------------------------------------------

def test_to_number():
    s = pd.Series(["1400", "1 400", "9,34", "74.57 USD", "", "null", "-", "мусор", "-12,5"])
    out = z.to_number(s)
    assert out.iloc[0] == 1400.0
    assert out.iloc[1] == 1400.0, "пробел-разделитель разрядов надо убрать"
    assert out.iloc[2] == pytest.approx(9.34), "запятая как десятичный разделитель"
    assert out.iloc[3] == pytest.approx(74.57), "валюту в строке надо отбросить"
    assert out.iloc[4:8].isna().all()
    assert out.iloc[8] == pytest.approx(-12.5), "минус сохраняется"
    assert pd.api.types.is_numeric_dtype(out)


# --- 4. parse_dates --------------------------------------------------------

def test_parse_dates():
    s = pd.Series(["2026-03-01", "01.03.2026", "2026-03-01 09:55:00",
                   "01.03.2026 09:55:00", "", "мусор", "31.12.2025"])
    out = z.parse_dates(s)
    assert out.iloc[0] == pd.Timestamp("2026-03-01"), \
        "ISO-дату нельзя разбирать с dayfirst — получится 3 января"
    assert out.iloc[1] == pd.Timestamp("2026-03-01")
    assert out.iloc[2] == pd.Timestamp("2026-03-01 09:55:00")
    assert out.iloc[3] == pd.Timestamp("2026-03-01 09:55:00")
    assert pd.isna(out.iloc[4]) and pd.isna(out.iloc[5])
    assert out.iloc[6] == pd.Timestamp("2025-12-31")


# --- 5. normalize_categorical ----------------------------------------------

def test_normalize_categorical():
    s = pd.Series(["iOS", "ANDROID", " Windows ", "pc", "", "null"])
    out = z.normalize_categorical(s, {"windows": "pc"})
    assert out.tolist()[:4] == ["ios", "android", "pc", "pc"]
    assert out.iloc[4:].isna().all()
    plain = z.normalize_categorical(pd.Series(["DE", "de", "Germany"]))
    assert plain.tolist() == ["de", "de", "germany"]


# --- 6. missing_report -----------------------------------------------------

def test_missing_report():
    df = pd.DataFrame({
        "a": [1, 2, 3, 4],
        "b": [1, None, None, None],
        "c": [None, None, 3, 4],
    })
    rep = z.missing_report(df)
    assert list(rep.columns) == ["column", "missing", "missing_pct"]
    assert len(rep) == 3
    assert rep.iloc[0]["column"] == "b", "сортировка по убыванию числа пропусков"
    assert rep.iloc[0]["missing"] == 3
    assert rep.iloc[0]["missing_pct"] == pytest.approx(75.0)
    assert rep[rep.column == "a"].iloc[0]["missing"] == 0


# --- 7. drop_dupes ---------------------------------------------------------

def test_drop_dupes():
    df = pd.DataFrame({
        "id": [1, 2, 3, 4],
        "a": ["x", "x", "y", "x"],
        "b": [10, 10, 20, 10],
    })
    out, removed = z.drop_dupes(df, ["a", "b"])
    assert removed == 2
    assert len(out) == 2
    assert out.iloc[0]["id"] == 1, "оставлять первое вхождение"
    assert list(out.index) == [0, 1], "индекс надо сбросить"


# --- 8. add_bucket ---------------------------------------------------------

def test_add_bucket():
    df = pd.DataFrame({"v": [5, 20, 49.9, 50, 250, None]})
    out = z.add_bucket(df, "v", [20, 50, 100],
                       ["1. до 20", "2. 20-50", "3. 50-100", "4. 100+"])
    assert "bucket" in out.columns
    vals = out["bucket"].astype("object").tolist()
    assert vals[0] == "1. до 20"
    assert vals[1] == "2. 20-50", "границы включают левый край"
    assert vals[2] == "2. 20-50"
    assert vals[3] == "3. 50-100"
    assert vals[4] == "4. 100+"
    assert pd.isna(vals[5])
    assert "v" in out.columns and len(out) == len(df)


# --- 9. revenue_by ---------------------------------------------------------

SALES = pd.DataFrame({
    "cat": ["a", "b", "a", "c", "b", None],
    "amount": [10.0, 50.0, 20.0, 5.0, 5.0, 7.0],
})


def test_revenue_by():
    out = z.revenue_by(SALES, "cat", "amount")
    assert out.index[0] == "b" and out.iloc[0] == 55.0
    assert out.loc["a"] == 30.0
    assert out.isna().sum() == 0
    assert len(out) == 4, "группа с пропущенным ключом не выбрасывается"


# --- 10. agg_multi ---------------------------------------------------------

def test_agg_multi():
    out = z.agg_multi(SALES, "cat", "amount")
    assert list(out.columns) == ["count", "total", "mean", "median"]
    assert out.loc["b", "count"] == 2
    assert out.loc["b", "total"] == 55.0
    assert out.loc["b", "mean"] == pytest.approx(27.5)
    assert out.index[0] == "b", "сортировка по убыванию суммы"


# --- 11. top_n_by ----------------------------------------------------------

def test_top_n_by():
    out = z.top_n_by(SALES, "cat", "amount", 2)
    assert len(out) == 2
    assert out.index.tolist() == ["b", "a"]


# --- 12. pivot_summary -----------------------------------------------------

def test_pivot_summary():
    df = pd.DataFrame({
        "city": ["x", "x", "y", "y"],
        "month": ["01", "02", "01", "01"],
        "amount": [1.0, 2.0, 3.0, 4.0],
    })
    out = z.pivot_summary(df, "city", "month", "amount")
    assert out.loc["x", "01"] == 1.0
    assert out.loc["y", "01"] == 7.0
    assert out.loc["y", "02"] == 0.0, "пустые комбинации заполняются нулём, а не NaN"


# --- 13. join_ltv ----------------------------------------------------------

def test_join_ltv():
    players = pd.DataFrame({"player_id": [1, 2, 3], "country": ["DE", "US", "BR"]})
    purchases = pd.DataFrame({
        "player_id": [1, 1, 3],
        "price": [10.0, 5.0, 20.0],
    })
    out = z.join_ltv(players, purchases)
    assert len(out) == 3, "число игроков не должно измениться после соединения"
    assert out.set_index("player_id").loc[1, "ltv"] == 15.0
    assert out.set_index("player_id").loc[2, "ltv"] == 0.0, \
        "у игрока без покупок LTV равен нулю, а не NaN"
    assert out.set_index("player_id").loc[2, "is_payer"] is np.False_ or \
        out.set_index("player_id").loc[2, "is_payer"] == False  # noqa: E712
    assert out["is_payer"].sum() == 2


# --- 14. monthly_series ----------------------------------------------------

def test_monthly_series():
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2026-01-05", "2026-01-20", "2026-03-02"]),
        "v": [1.0, 2.0, 5.0],
    })
    out = z.monthly_series(df, "ts", "v")
    assert len(out) == 3, "февраль должен присутствовать, хотя данных за него нет"
    assert out.iloc[0] == 3.0
    assert out.iloc[1] == 0.0
    assert out.iloc[2] == 5.0


# --- 15. share_of_total ----------------------------------------------------

def test_share_of_total():
    s = pd.Series({"a": 30.0, "b": 70.0})
    out = z.share_of_total(s)
    assert out["a"] == pytest.approx(30.0)
    assert out["b"] == pytest.approx(70.0)
    assert z.share_of_total(pd.Series([0.0, 0.0])).sum() == 0.0, \
        "деление на ноль не должно ломать функцию"


# --- 16. detect_outliers_iqr -----------------------------------------------

def test_detect_outliers_iqr():
    s = pd.Series([10, 11, 12, 13, 14, 15, 16, 200])
    out = z.detect_outliers_iqr(s)
    assert out.dtype == bool
    assert out.iloc[-1] is np.True_ or out.iloc[-1] == True  # noqa: E712
    assert out.sum() == 1
    assert not z.detect_outliers_iqr(pd.Series([1, 2, 3, 4])).any()
