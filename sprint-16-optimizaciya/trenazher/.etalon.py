"""Эталонные решения тренажёра спринта 16. Не подглядывать до решения."""

import re
from collections import defaultdict, deque

import numpy as np
import pandas as pd

REMOVED_RE = re.compile(r"^\s*Rows Removed by (?:Filter|Join Filter|Index Recheck):\s+(\d+)")

NODE_RE = re.compile(
    r"^(?P<indent>\s*)(?:->\s+)?(?P<name>[A-Z][A-Za-z\- ]*?)"
    r"(?:\s+on\s+(?P<table>[\w.]+)(?:\s+\w+)?)?"
    r"\s+\(cost=(?P<c1>[\d.]+)\.\.(?P<c2>[\d.]+)\s+rows=(?P<erows>\d+)\s+width=\d+\)"
    r"(?:\s+\(actual time=(?P<t1>[\d.]+)\.\.(?P<t2>[\d.]+)\s+rows=(?P<arows>[\d.]+)"
    r"\s+loops=(?P<loops>\d+)\))?"
)


# --- чтение планов ---------------------------------------------------------

def parse_plan(text):
    """Разбор текстового EXPLAIN (ANALYZE) в список узлов с глубиной."""
    raw = []
    for line in text.splitlines():
        m = NODE_RE.match(line)
        if m:
            raw.append(m.groupdict())
            continue
        rm = REMOVED_RE.match(line)
        if rm and raw:
            raw[-1]["removed"] = rm.group(1)
    ranks = {v: i for i, v in enumerate(sorted({len(g["indent"]) for g in raw}))}
    nodes = []
    for g in raw:
        indent = len(g["indent"])
        loops = int(g["loops"]) if g["loops"] else 1
        total = float(g["t2"]) * loops if g["t2"] else None
        nodes.append({
            "node": g["name"].strip(),
            "table": g["table"],
            "depth": ranks[indent],
            "cost": float(g["c2"]),
            "est_rows": int(g["erows"]),
            "act_rows": float(g["arows"]) * loops if g["arows"] else None,
            "loops": loops,
            "total_ms": total,
            "removed_rows": float(g.get("removed") or 0) * loops,
            "rows_scanned": (float(g["arows"]) + float(g.get("removed") or 0)) * loops
            if g["arows"] else None,
        })
    return nodes


def plan_bottleneck(nodes):
    """Узел с наибольшим СОБСТВЕННЫМ временем.

    Время узла в плане включает время потомков, поэтому собственное время —
    это разница между узлом и суммой его прямых детей.
    """
    if not nodes:
        return None
    self_ms = []
    for i, n in enumerate(nodes):
        if n["total_ms"] is None:
            self_ms.append(None)
            continue
        kids = 0.0
        for j in range(i + 1, len(nodes)):
            if nodes[j]["depth"] <= n["depth"]:
                break
            if nodes[j]["depth"] == n["depth"] + 1 and nodes[j]["total_ms"]:
                kids += nodes[j]["total_ms"]
        self_ms.append(max(0.0, n["total_ms"] - kids))
    known = [(v, i) for i, v in enumerate(self_ms) if v is not None]
    if not known:
        return None
    _, idx = max(known)
    out = dict(nodes[idx])
    out["self_ms"] = self_ms[idx]
    out["share"] = (self_ms[idx] / nodes[0]["total_ms"]
                    if nodes[0]["total_ms"] else None)
    return out


def estimate_error(nodes, threshold=10.0):
    """Узлы, где планировщик ошибся в оценке числа строк.

    Коэффициент — во сколько раз факт отличается от оценки, всегда >= 1.
    """
    out = []
    for n in nodes:
        if n["act_rows"] is None:
            continue
        est = max(n["est_rows"], 1)
        act = max(n["act_rows"], 1)
        ratio = max(est / act, act / est)
        if ratio >= threshold:
            out.append({"node": n["node"], "table": n["table"],
                        "est_rows": n["est_rows"], "act_rows": n["act_rows"],
                        "ratio": ratio,
                        "direction": "недооценил" if act > est else "переоценил"})
    return sorted(out, key=lambda r: -r["ratio"])


def find_seq_scans(nodes, min_rows=100000):
    """Последовательные сканы больших таблиц."""
    out = []
    for n in nodes:
        if not n["node"].startswith("Seq Scan"):
            continue
        rows = (n["rows_scanned"] if n["rows_scanned"] is not None
                else float(n["est_rows"]))
        if rows >= min_rows:
            out.append({"table": n["table"], "rows": rows,
                        "returned": n["act_rows"],
                        "total_ms": n["total_ms"], "loops": n["loops"]})
    return sorted(out, key=lambda r: -r["rows"])


# --- индексы ---------------------------------------------------------------

def index_usable(predicate):
    """Сможет ли B-tree индекс по столбцу обслужить предикат.

    Возвращает {'usable', 'reason', 'column'}.
    """
    low = predicate.strip().lower()

    func_m = re.match(r"^(\w+)\s*\((.*?)\)", low)
    if func_m:
        inner = re.sub(r"'[^']*'", "", func_m.group(2))
        tokens = re.findall(r"[a-z_][\w.]*", inner)
        col = tokens[0] if tokens else None
        return {"usable": False, "column": col,
                "reason": "функция на столбце: индекс по столбцу не подходит, "
                          "нужен индекс по выражению или перепись под диапазон"}

    cast_m = re.match(r"^([\w.]+)\s*::", low)
    if cast_m:
        return {"usable": False, "column": cast_m.group(1),
                "reason": "приведение типа на столбце ломает индекс"}

    like_m = re.match(r"^([\w.]+)\s+like\s+'(.*)'$", low)
    if like_m:
        pattern = like_m.group(2)
        if pattern.startswith("%") or pattern.startswith("_"):
            return {"usable": False, "column": like_m.group(1),
                    "reason": "LIKE без якоря слева: B-tree не помогает, "
                              "нужен триграммный индекс"}
        return {"usable": True, "column": like_m.group(1),
                "reason": "LIKE с якорем слева работает как диапазон"}

    col_m = re.match(
        r"^([\w.]+)\s*(?:<=|>=|<>|!=|=|<|>|\bbetween\b|\bin\b)", low)
    if col_m:
        return {"usable": True, "column": col_m.group(1),
                "reason": "предикат по столбцу напрямую"}
    return {"usable": False, "column": None, "reason": "предикат не разобран"}


def composite_order(equality, ranges, order_by=None):
    """Порядок столбцов составного индекса: равенство, диапазон, сортировка."""
    seen, cols = set(), []
    for group in (list(equality), list(ranges), list(order_by or [])):
        for c in group:
            if c not in seen:
                seen.add(c)
                cols.append(c)
    warning = ""
    if ranges and order_by:
        warning = ("после столбца с диапазонным предикатом индекс уже не даёт "
                   "порядок: сортировку придётся делать отдельно")
    return {"columns": cols,
            "definition": f"({', '.join(cols)})",
            "warning": warning,
            "rule": "сначала равенство, потом диапазон, потом сортировка"}


def index_write_cost(table_rows, writes_per_day, index_bytes_per_row=24,
                     n_indexes_before=1):
    """Во что обходится ещё один индекс: место и накладные на запись."""
    size_mb = table_rows * index_bytes_per_row / 1024 / 1024
    before, after = n_indexes_before, n_indexes_before + 1
    overhead = (after - before) / max(before, 1)
    return {"size_mb": size_mb,
            "writes_per_day": int(writes_per_day),
            "index_updates_per_day": int(writes_per_day),
            "write_overhead_pct": 100 * overhead,
            "indexes_after": after}


# --- моделирование ---------------------------------------------------------

def grain_check(df, grain_cols):
    """Соответствует ли таблица заявленной зернистости."""
    dup = df.duplicated(subset=list(grain_cols), keep=False)
    n = int(dup.sum())
    ex = df.loc[dup, list(grain_cols)].drop_duplicates().head(3).to_dict("records")
    return {"grain": list(grain_cols), "rows": int(len(df)),
            "unique_keys": int(df[list(grain_cols)].drop_duplicates().shape[0]),
            "violating_rows": n, "ok": n == 0, "examples": ex}


def star_schema_check(fact, dimensions, fact_key_cols=None):
    """Проверка звезды: у каждого ключа факта есть измерение, нет сирот."""
    problems, checked = [], []
    keys = list(fact_key_cols) if fact_key_cols else [
        c for c in fact.columns if c.endswith("_id")]
    for k in keys:
        if k not in dimensions:
            problems.append(f"нет измерения для ключа {k}")
            continue
        dim = dimensions[k]
        dim_key = k if k in dim.columns else dim.columns[0]
        orphans = int((~fact[k].dropna().isin(set(dim[dim_key]))).sum())
        checked.append({"key": k, "orphans": orphans})
        if orphans:
            problems.append(f"{orphans} строк факта без измерения по {k}")
    return {"keys": keys, "checked": checked, "problems": problems,
            "ok": len(problems) == 0}


def scd2_apply(dim, key, key_col, attrs, valid_from,
               from_col="valid_from", to_col="valid_to",
               current_col="is_current"):
    """Изменение атрибута в SCD2: закрыть текущую версию, открыть новую.

    Если атрибуты не изменились, ничего не делается — иначе таблица растёт
    от каждого прогона загрузки.
    """
    d = dim.copy()
    ts = pd.Timestamp(valid_from)
    for c in (from_col, to_col):
        if c in d.columns:
            d[c] = pd.to_datetime(d[c])
    mask = (d[key_col] == key) & (d[current_col].astype(bool))
    if mask.any():
        cur = d.loc[mask].iloc[0]
        if all(cur.get(k) == v for k, v in attrs.items()):
            return {"changed": False, "table": d,
                    "reason": "атрибуты не изменились"}
        d.loc[mask, to_col] = ts
        d.loc[mask, current_col] = False
    row = {key_col: key, from_col: ts, to_col: pd.NaT, current_col: True}
    row.update(attrs)
    d = pd.concat([d, pd.DataFrame([row])], ignore_index=True)
    return {"changed": True, "table": d, "reason": "открыта новая версия"}


def scd2_lookup(dim, key, key_col, on_date, attr,
                from_col="valid_from", to_col="valid_to"):
    """Значение атрибута на конкретную дату."""
    d = dim.copy()
    d[from_col] = pd.to_datetime(d[from_col])
    d[to_col] = pd.to_datetime(d[to_col])
    ts = pd.Timestamp(on_date)
    m = ((d[key_col] == key) & (d[from_col] <= ts)
         & (d[to_col].isna() | (d[to_col] > ts)))
    if not m.any():
        return None
    return d.loc[m].iloc[0][attr]


# --- ETL -------------------------------------------------------------------

def incremental_window(last_loaded, now, lookback_hours=3, max_window_days=7):
    """Окно инкрементальной загрузки с перекрытием на поздние данные."""
    last = pd.Timestamp(last_loaded)
    now = pd.Timestamp(now)
    start = last - pd.Timedelta(hours=lookback_hours)
    capped = False
    if (now - start) > pd.Timedelta(days=max_window_days):
        start = now - pd.Timedelta(days=max_window_days)
        capped = True
    return {"start": start, "end": now,
            "hours": (now - start).total_seconds() / 3600,
            "capped": capped,
            "overlap_hours": 0.0 if capped else float(lookback_hours)}


def merge_upsert(target, batch, key_cols):
    """Идемпотентное применение батча: обновить существующие, добавить новые."""
    keys = list(key_cols)
    t = target.copy()
    b = batch.drop_duplicates(subset=keys, keep="last").copy()
    idx = pd.MultiIndex.from_frame(t[keys]) if len(t) else pd.MultiIndex.from_arrays(
        [[] for _ in keys], names=keys)
    bidx = pd.MultiIndex.from_frame(b[keys])
    updated = int(bidx.isin(idx).sum())
    inserted = int(len(b) - updated)
    merged = pd.concat([t, b], ignore_index=True)
    merged = merged.drop_duplicates(subset=keys, keep="last").reset_index(drop=True)
    merged = merged.sort_values(keys).reset_index(drop=True)
    return {"table": merged, "updated": updated, "inserted": inserted,
            "rows_after": int(len(merged))}


def is_idempotent(func, target, batch, key_cols, times=3):
    """Проверка идемпотентности: повторный прогон не меняет результат."""
    first = func(target, batch, key_cols)["table"]
    out = first
    for _ in range(times - 1):
        out = func(out, batch, key_cols)["table"]
    same = first.reset_index(drop=True).equals(out.reset_index(drop=True))
    return {"idempotent": bool(same), "rows_first": int(len(first)),
            "rows_after_repeats": int(len(out)), "runs": times}


def late_arriving(batch, ts_col="event_ts", partition="D"):
    """Какие партиции придётся пересчитать из-за поздно пришедших данных."""
    ts = pd.to_datetime(batch[ts_col])
    if len(ts) == 0:
        return {"partitions": [], "n_partitions": 0, "oldest": None,
                "span_days": 0}
    parts = sorted(ts.dt.to_period(partition).unique())
    oldest = ts.min()
    span = (ts.max().normalize() - oldest.normalize()).days
    return {"partitions": [str(p) for p in parts],
            "n_partitions": len(parts),
            "oldest": oldest, "span_days": int(span)}


def backfill_plan(date_from, date_to, batch_days=7, freq="D"):
    """Разбиение перезаливки на батчи, чтобы не положить базу одним запросом."""
    start, end = pd.Timestamp(date_from), pd.Timestamp(date_to)
    if start > end:
        raise ValueError("date_from позже date_to")
    batches, cur = [], start
    step = pd.Timedelta(days=batch_days)
    while cur <= end:
        stop = min(cur + step - pd.Timedelta(days=1), end)
        batches.append({"from": cur, "to": stop,
                        "days": (stop - cur).days + 1})
        cur = stop + pd.Timedelta(days=1)
    return {"batches": batches, "n_batches": len(batches),
            "total_days": (end - start).days + 1}


def pipeline_order(deps):
    """Порядок пересчёта моделей: топологическая сортировка. Цикл — ValueError."""
    nodes = set(deps) | {d for v in deps.values() for d in v}
    indeg = {n: 0 for n in nodes}
    children = defaultdict(list)
    for node, parents in deps.items():
        for p in parents:
            children[p].append(node)
            indeg[node] += 1
    q = deque(sorted(n for n in nodes if indeg[n] == 0))
    order, levels, level = [], {}, 0
    for n in q:
        levels[n] = 0
    while q:
        n = q.popleft()
        order.append(n)
        for c in sorted(children[n]):
            indeg[c] -= 1
            levels[c] = max(levels.get(c, 0), levels[n] + 1)
            if indeg[c] == 0:
                q.append(c)
    if len(order) != len(nodes):
        stuck = sorted(n for n in nodes if n not in order)
        raise ValueError(f"цикл в зависимостях: {stuck}")
    by_level = defaultdict(list)
    for n in order:
        by_level[levels[n]].append(n)
    return {"order": order, "levels": {k: sorted(v) for k, v in by_level.items()},
            "max_parallel": max(len(v) for v in by_level.values()) if by_level else 0}


# --- диагноз ---------------------------------------------------------------

def explain_verdict(nodes, big_table_rows=100000, estimate_threshold=10.0,
                    selectivity_threshold=0.05):
    """Диагноз по плану: что не так и что с этим делать."""
    findings = []
    for n in nodes:
        scanned = n["rows_scanned"]
        if n["node"].startswith("Seq Scan") and scanned and scanned >= big_table_rows:
            returned = n["act_rows"] or 0
            sel = returned / scanned if scanned else 1.0
            if sel <= selectivity_threshold:
                findings.append({
                    "node": n["node"], "table": n["table"],
                    "problem": "последовательный скан большой таблицы ради "
                               "малой доли строк",
                    "evidence": f"просмотрено {scanned:.0f}, возвращено "
                                f"{returned:.0f} ({100 * sel:.3f}%)",
                    "fix": "индекс по столбцу фильтра, либо предикат, который "
                           "индекс может использовать"})
        if n["loops"] > 1 and scanned and scanned >= big_table_rows:
            findings.append({
                "node": n["node"], "table": n["table"],
                "problem": "узел выполняется многократно",
                "evidence": f"{n['loops']} проходов, суммарно {scanned:.0f} строк",
                "fix": "переписать коррелированный подзапрос через соединение "
                       "с агрегацией, либо добавить индекс по ключу связи"})
        if n["act_rows"] is not None:
            est, act = max(n["est_rows"], 1), max(n["act_rows"], 1)
            ratio = max(est / act, act / est)
            if ratio >= estimate_threshold:
                findings.append({
                    "node": n["node"], "table": n["table"],
                    "problem": "планировщик ошибся в оценке числа строк",
                    "evidence": f"ожидал {n['est_rows']}, получил "
                                f"{n['act_rows']:.0f} — в {ratio:.0f} раз",
                    "fix": "ANALYZE, расширенная статистика по связанным "
                           "столбцам, либо предикат, который статистика умеет "
                           "оценивать"})
    seen, unique = set(), []
    for f in findings:
        k = (f["node"], f["table"], f["problem"])
        if k not in seen:
            seen.add(k)
            unique.append(f)
    return {"findings": unique, "n": len(unique),
            "clean": len(unique) == 0}
