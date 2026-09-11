"""Эталонные решения тренажёра спринта 17. Не подглядывать до решения."""

import math

import numpy as np
import pandas as pd

INT_TYPES = [(255, "UInt8"), (65535, "UInt16"), (4294967295, "UInt32"),
             (18446744073709551615, "UInt64")]


# --- проектирование таблицы ------------------------------------------------

def choose_order_by(queries, columns, max_cols=4):
    """ORDER BY по набору запросов: сначала частые фильтры низкой кардинальности.

    queries — [{'filters': [...], 'group_by': [...]}].
    columns — {имя: кардинальность}.
    """
    weight = {}
    for q in queries:
        for c in q.get("filters", []):
            weight[c] = weight.get(c, 0) + 2
        for c in q.get("group_by", []):
            weight[c] = weight.get(c, 0) + 1
    cand = [c for c in weight if c in columns]
    cand.sort(key=lambda c: (-weight[c], columns[c], c))
    chosen = cand[:max_cols]
    return {"order_by": chosen,
            "definition": f"ORDER BY ({', '.join(chosen)})" if chosen else "ORDER BY tuple()",
            "weights": weight,
            "rule": "первым — столбец, по которому фильтруют чаще и у которого "
                    "меньше уникальных значений"}


def partition_expr(ts_col, rows_per_day, retention_days, target_parts=(10, 1000)):
    """Выражение партиционирования: месяц, неделя или день.

    Партиций должно быть немного: их число — это накладные расходы.
    """
    options = [("toYYYYMM", 30), ("toMonday", 7), ("toDate", 1)]
    best = None
    for func, days in options:
        n = max(1, math.ceil(retention_days / days))
        rows = rows_per_day * days
        ok = target_parts[0] <= n <= target_parts[1]
        cand = {"func": func, "days_per_part": days, "parts": n,
                "rows_per_part": rows, "ok": ok}
        if ok and (best is None or n < best["parts"]):
            best = cand
    if best is None:
        best = {"func": "toYYYYMM", "days_per_part": 30,
                "parts": max(1, math.ceil(retention_days / 30)),
                "rows_per_part": rows_per_day * 30, "ok": False}
    return {"expression": f"PARTITION BY {best['func']}({ts_col})",
            "func": best["func"], "parts": best["parts"],
            "rows_per_part": best["rows_per_part"],
            "within_target": best["ok"]}


def pick_type(name, sample, nullable_ok=False):
    """Тип столбца ClickHouse по образцу значений."""
    s = pd.Series(list(sample))
    has_null = bool(s.isna().any())
    clean = s.dropna()
    if len(clean) == 0:
        return {"type": "String", "reason": "нет значений, чтобы судить"}

    if pd.api.types.is_datetime64_any_dtype(clean) or (
            clean.map(lambda v: isinstance(v, (pd.Timestamp,))).all()):
        t, reason = "DateTime", "секундной точности достаточно"
    elif clean.map(lambda v: isinstance(v, (bool, np.bool_))).all():
        t, reason = "UInt8", "булево хранится как UInt8"
    elif pd.api.types.is_integer_dtype(clean):
        lo, hi = int(clean.min()), int(clean.max())
        if lo < 0:
            width = next(w for lim, w in
                         [(127, "Int8"), (32767, "Int16"), (2147483647, "Int32")]
                         if max(abs(lo), hi) <= lim) if max(abs(lo), hi) <= 2147483647 else "Int64"
            t, reason = width, "есть отрицательные значения"
        else:
            t = next((w for lim, w in INT_TYPES if hi <= lim), "UInt64")
            reason = f"максимум {hi} помещается в {t}"
    elif pd.api.types.is_float_dtype(clean):
        t, reason = "Decimal(10, 2)", "деньги хранят Decimal, а не Float"
    else:
        uniq = clean.nunique()
        if uniq <= 10000 and uniq / len(clean) < 0.5:
            t = "LowCardinality(String)"
            reason = f"{uniq} уникальных значений — словарное сжатие выгодно"
        else:
            t, reason = "String", f"{uniq} уникальных — словарь не поможет"

    if has_null:
        if nullable_ok:
            return {"type": f"Nullable({t})", "reason": reason + "; пропуски разрешены"}
        return {"type": t, "reason": reason +
                "; пропуски заменить значением по умолчанию, Nullable дорог"}
    return {"type": t, "reason": reason}


def engine_for(task):
    """Движок таблицы по задаче."""
    table = {
        "append": ("MergeTree", "только дописывание, ничего не схлопывается"),
        "dedup": ("ReplacingMergeTree", "дубли по ключу схлопываются, "
                                        "побеждает строка с большей версией"),
        "sum": ("SummingMergeTree", "числовые столбцы складываются по ключу"),
        "aggregate": ("AggregatingMergeTree", "хранит состояния агрегатов, "
                                              "нужен -State при записи и -Merge при чтении"),
        "log": ("MergeTree", "поток событий — обычный MergeTree"),
    }
    if task not in table:
        raise ValueError(f"неизвестная задача: {task}")
    engine, reason = table[task]
    return {"engine": engine, "reason": reason,
            "warning": ("схлопывание происходит в фоне и не гарантировано "
                        "к моменту чтения: нужен FINAL или GROUP BY")
            if engine != "MergeTree" else ""}


def ddl_for(table, columns, engine, order_by, partition_by=None, ttl=None):
    """Сборка CREATE TABLE."""
    lines = [f"CREATE TABLE {table}", "("]
    width = max(len(c) for c in columns)
    body = [f"    {c.ljust(width)}  {t}" for c, t in columns.items()]
    lines.append(",\n".join(body))
    lines.append(")")
    lines.append(f"ENGINE = {engine}")
    if partition_by:
        lines.append(f"PARTITION BY {partition_by}")
    lines.append(f"ORDER BY ({', '.join(order_by)})" if order_by else "ORDER BY tuple()")
    if ttl:
        lines.append(f"TTL {ttl}")
    return "\n".join(lines)


# --- массивы ---------------------------------------------------------------

def array_join(df, array_col):
    """Аналог arrayJoin: строка с массивом разворачивается в строки."""
    out = df.explode(array_col).reset_index(drop=True)
    return out[out[array_col].notna()].reset_index(drop=True)


def array_filter_map(values, predicate, transform):
    """arrayFilter и arrayMap: сначала отбор, потом преобразование."""
    return [transform(v) for v in values if predicate(v)]


def events_to_array(events, user_col="user_id", name_col="event_name",
                    ts_col="ts"):
    """Свернуть события пользователя в массивы — типичный приём ClickHouse.

    Одна строка на пользователя: массив событий и массив времён,
    отсортированные по времени.
    """
    e = events[[user_col, name_col, ts_col]].copy()
    e[ts_col] = pd.to_datetime(e[ts_col])
    e = e.sort_values([user_col, ts_col])
    g = e.groupby(user_col, sort=True)
    out = pd.DataFrame({
        user_col: list(g.groups),
        "names": [list(v) for v in g[name_col].apply(list)],
        "times": [list(v) for v in g[ts_col].apply(list)],
    })
    out["n"] = out["names"].map(len)
    return out


def has_sequence(names, pattern):
    """Есть ли в массиве подпоследовательность pattern (не обязательно подряд)."""
    it = iter(names)
    return all(any(x == step for x in it) for step in pattern)


# --- комбинаторы и приближённые агрегаты -----------------------------------

def combinator_name(func, combinators):
    """Сборка имени агрегатной функции с комбинаторами.

    Порядок фиксирован: -Array, -If, -OrNull/-OrDefault, -State/-Merge.
    """
    order = ["Array", "If", "OrNull", "OrDefault", "State", "Merge"]
    unknown = [c for c in combinators if c not in order]
    if unknown:
        raise ValueError(f"неизвестные комбинаторы: {sorted(unknown)}")
    if "State" in combinators and "Merge" in combinators:
        raise ValueError("State и Merge вместе не имеют смысла")
    tail = "".join(c for c in order if c in combinators)
    return {"name": func + tail, "func": func,
            "combinators": [c for c in order if c in combinators]}


def agg_if(values, flags, how="sum"):
    """Аналог sumIf / countIf / avgIf: агрегат по строкам, где флаг истинен."""
    v = pd.Series(list(values), dtype="float64")
    f = pd.Series(list(flags)).astype(bool)
    sel = v[f.values]
    if how == "sum":
        return float(sel.sum())
    if how == "count":
        return int(sel.count())
    if how == "avg":
        return float(sel.mean()) if len(sel) else None
    if how == "max":
        return float(sel.max()) if len(sel) else None
    raise ValueError(f"неизвестная агрегация: {how}")


def uniq_error(exact, approx):
    """Ошибка приближённого счёта уникальных и вердикт о применимости."""
    exact, approx = float(exact), float(approx)
    if exact == 0:
        return {"exact": 0.0, "approx": approx, "abs_error": approx,
                "rel_error": None, "acceptable": approx == 0}
    rel = abs(approx - exact) / exact
    return {"exact": exact, "approx": approx,
            "abs_error": abs(approx - exact), "rel_error": rel,
            "acceptable": rel <= 0.01,
            "verdict": "приближённого достаточно" if rel <= 0.01
                       else "нужен точный подсчёт"}


def uniq_choice(rows, need_exact, latency_budget_s):
    """Какую функцию уникальных выбрать."""
    if need_exact:
        return {"function": "uniqExact", "reason": "точность обязательна: "
                "биллинг, юридическая отчётность, сверка с внешней системой",
                "approximate": False}
    if rows >= 10_000_000 and latency_budget_s < 1.0:
        return {"function": "uniq", "reason": "HyperLogLog: ошибка около "
                "процента, памяти константа", "approximate": True}
    if rows >= 1_000_000:
        return {"function": "uniqCombined", "reason": "точнее uniq на средних "
                "объёмах, дороже по памяти", "approximate": True}
    return {"function": "uniqExact", "reason": "объём маленький, точность "
            "ничего не стоит", "approximate": False}


def quantile_choice(rows, need_exact, is_latency=False):
    """Вариант quantile под задачу."""
    if is_latency:
        return {"function": "quantileTiming",
                "reason": "оптимизирован под времена ответа в миллисекундах"}
    if need_exact:
        return {"function": "quantileExact",
                "reason": "точный, держит все значения в памяти"}
    if rows >= 10_000_000:
        return {"function": "quantileTDigest",
                "reason": "приближённый, память ограничена"}
    return {"function": "quantile", "reason": "по умолчанию, приближённый"}


# --- воронки ---------------------------------------------------------------

def window_funnel(events, steps, window_seconds, user_col="user_id",
                  name_col="event_name", ts_col="ts"):
    """Аналог windowFunnel: максимальный достигнутый уровень для пользователя.

    Шаги должны идти по возрастанию времени, и ВСЯ цепочка должна уложиться
    в окно window_seconds от первого шага. Возвращает {user_id: level}.
    """
    e = events[[user_col, name_col, ts_col]].copy()
    e[ts_col] = pd.to_datetime(e[ts_col])
    e = e.sort_values([user_col, ts_col])
    result = {}
    for uid, g in e.groupby(user_col, sort=True):
        names = list(g[name_col])
        times = list(g[ts_col])
        best = 0
        for i, (n0, t0) in enumerate(zip(names, times)):
            if n0 != steps[0]:
                continue
            level, want, deadline = 1, 1, t0 + pd.Timedelta(seconds=window_seconds)
            for n, t in zip(names[i + 1:], times[i + 1:]):
                if t > deadline:
                    break
                if want < len(steps) and n == steps[want]:
                    want += 1
                    level += 1
                    if level == len(steps):
                        break
            best = max(best, level)
            if best == len(steps):
                break
        result[uid] = best
    return result


def funnel_levels_to_cumulative(levels, n_steps):
    """Из распределения максимальных уровней — кумулятивная воронка.

    windowFunnel возвращает «докуда дошёл каждый», а воронка показывает
    «сколько дошло хотя бы до шага N». Это разные числа.
    """
    counts = {i: 0 for i in range(n_steps + 1)}
    for lvl in levels.values():
        counts[int(lvl)] = counts.get(int(lvl), 0) + 1
    rows, running = [], 0
    for step in range(n_steps, 0, -1):
        running += counts.get(step, 0)
        rows.append({"step": step, "users": running})
    rows.reverse()
    top = rows[0]["users"] if rows else 0
    prev = None
    for r in rows:
        r["from_top"] = round(100 * r["users"] / top, 2) if top else None
        r["step_cr"] = None if prev in (None, 0) else round(100 * r["users"] / prev, 2)
        prev = r["users"]
    return pd.DataFrame(rows)


def retention_ch(conditions):
    """Аналог retention(): первое условие — база, остальные считаются только с ней.

    conditions — список списков булевых значений одинаковой длины:
    по одному списку на условие, по одному элементу на строку.
    """
    if not conditions:
        return []
    base = [bool(x) for x in conditions[0]]
    out = [sum(base)]
    for cond in conditions[1:]:
        out.append(sum(1 for b, c in zip(base, cond) if b and c))
    return out


# --- эксплуатация ----------------------------------------------------------

def ttl_expr(ts_col, keep_days, rollup_days=None, rollup_to=None):
    """Выражение TTL: удаление старого и, опционально, перенос на холодный диск."""
    parts = []
    if rollup_days is not None and rollup_to:
        if rollup_days >= keep_days:
            raise ValueError("перенос должен происходить раньше удаления")
        parts.append(f"{ts_col} + INTERVAL {rollup_days} DAY TO VOLUME '{rollup_to}'")
    parts.append(f"{ts_col} + INTERVAL {keep_days} DAY DELETE")
    return {"expression": "TTL " + ", ".join(parts), "keep_days": int(keep_days),
            "moves": rollup_to is not None}


def mutation_cost(table_rows, part_count, changed_columns, total_columns,
                  bytes_per_row=100):
    """Во что обходится ALTER UPDATE / DELETE в ClickHouse.

    Мутация не правит строки на месте: она переписывает куски целиком.
    """
    share = changed_columns / total_columns if total_columns else 1.0
    rewritten_mb = table_rows * bytes_per_row / 1024 / 1024
    return {"parts_to_rewrite": int(part_count),
            "rows_rewritten": int(table_rows),
            "rewritten_mb": rewritten_mb,
            "changed_share": share,
            "asynchronous": True,
            "warning": "мутация переписывает куски целиком и выполняется в "
                       "фоне; system.mutations показывает прогресс, отменить "
                       "можно только KILL MUTATION"}
