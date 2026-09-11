"""Эталонные решения тренажёра спринта 7. Не подглядывать до решения."""

import csv
from datetime import timedelta


def parse_price(raw):
    if raw is None:
        return None
    s = str(raw).strip().replace(" ", "").replace(" ", "")
    s = s.replace("р.", "").replace("руб.", "").replace("₽", "")
    s = s.replace(",", ".")
    if s.count(".") > 1:
        head, _, tail = s.rpartition(".")
        s = head.replace(".", "") + "." + tail
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def normalize_name(raw):
    if raw is None:
        return None
    return " ".join(str(raw).split()).lower()


def parse_date(raw):
    s = str(raw).strip()
    if "." in s:
        d, m, y = s.split(".")
        return (int(y), int(m), int(d))
    y, m, d = s.split("-")
    return (int(y), int(m), int(d))


def count_by(records, key):
    result = {}
    for r in records:
        result[r.get(key)] = result.get(r.get(key), 0) + 1
    return result


def sum_by(records, key, value_key):
    result = {}
    for r in records:
        v = r.get(value_key)
        if v is None:
            continue
        result[r.get(key)] = result.get(r.get(key), 0) + v
    return result


def dedupe(records, keys):
    seen = set()
    out = []
    for r in records:
        k = tuple(r.get(x) for x in keys)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def median(values):
    vals = sorted(v for v in values if v is not None)
    n = len(vals)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return float(vals[mid])
    return (vals[mid - 1] + vals[mid]) / 2


def percentile(values, p):
    vals = sorted(v for v in values if v is not None)
    n = len(vals)
    if n == 0:
        return None
    if n == 1:
        return float(vals[0])
    pos = (n - 1) * p
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return vals[lo] + (vals[hi] - vals[lo]) * frac


def top_n(counts, n):
    return sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))[:n]


def conversion_funnel(steps):
    out = []
    prev = None
    for name, users in steps:
        cr = None if prev is None else (None if prev == 0 else round(100 * users / prev, 1))
        out.append((name, users, cr))
        prev = users
    return out


def moving_average(values, window):
    out = []
    for i in range(len(values)):
        chunk = values[max(0, i - window + 1): i + 1]
        out.append(round(sum(chunk) / len(chunk), 4))
    return out


def bucketize(value, bounds, labels):
    if value is None:
        return None
    for i, b in enumerate(bounds):
        if value < b:
            return labels[i]
    return labels[-1]


def group_values(records, key, value_key):
    out = {}
    for r in records:
        out.setdefault(r.get(key), []).append(r.get(value_key))
    return out


def fill_missing_dates(date_counts, start, end):
    out = {}
    cur = start
    while cur <= end:
        out[cur] = date_counts.get(cur, 0)
        cur += timedelta(days=1)
    return out


def flatten(nested):
    out = []
    for item in nested:
        if isinstance(item, list):
            out.extend(flatten(item))
        else:
            out.append(item)
    return out


def parse_utm(url):
    if "?" not in url:
        return {}
    query = url.split("?", 1)[1].split("#", 1)[0]
    out = {}
    for part in query.split("&"):
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        if k.startswith("utm_"):
            out[k] = v
    return out


def retention_day_n(regs, sessions, n):
    active = set()
    for user_id, day in sessions:
        active.add((user_id, day))
    total = len(regs)
    if total == 0:
        return None
    retained = sum(1 for uid, reg in regs.items() if (uid, reg + timedelta(days=n)) in active)
    return round(100 * retained / total, 1)


def safe_div(a, b, default=None):
    if b in (0, None) or a is None:
        return default
    return a / b


def read_csv_rows(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def summarize(path):
    rows = read_csv_rows(path)
    # порядок важен: сначала приводим имя к канону, потом ищем дубликаты.
    # Наоборот дубликат с висящим пробелом не найдётся.
    normalized = []
    for r in rows:
        r = dict(r)
        r["master"] = normalize_name(r["master"])
        normalized.append(r)
    clean = dedupe(normalized, ["data", "vremya", "master", "id_klienta"])
    done = [r for r in clean if r["status"] == "выполнена"]
    prices = [parse_price(r["cena"]) for r in done]
    prices = [p for p in prices if p is not None]
    return {
        "rows": len(rows),
        "after_dedupe": len(clean),
        "completed": len(done),
        "revenue": round(sum(prices), 2),
        "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
        "median_price": median(prices),
        "masters": len({r["master"] for r in clean}),
    }
