#!/usr/bin/env python3
"""
Датасет итогового проекта модуля 3: венчурные сделки.

Пять связанных CSV — как выгрузка из базы вроде Crunchbase.
Запуск: python3 generate_venture.py
"""
import csv, os, random
from datetime import date, timedelta

rnd = random.Random(3033)
HERE = os.path.dirname(os.path.abspath(__file__))
START = date(2014, 1, 1)
END = date(2026, 6, 30)

CATEGORIES = [
    ("fintech", .13), ("saas", .15), ("healthtech", .10), ("ecommerce", .11),
    ("ai/ml", .12), ("edtech", .06), ("logistics", .06), ("gaming", .05),
    ("cybersecurity", .06), ("proptech", .04), ("foodtech", .05),
    ("cleantech", .04), ("hrtech", .03),
]
COUNTRIES = [
    ("USA", .34), ("GBR", .09), ("DEU", .07), ("FRA", .05), ("ISR", .05),
    ("IND", .07), ("CHN", .06), ("CAN", .04), ("SWE", .03), ("NLD", .03),
    ("SGP", .03), ("BRA", .03), ("POL", .02), ("ARE", .02), ("EST", .02),
    (None, .05),
]
CITY_BY_COUNTRY = {
    "USA": ["San Francisco", "New York", "Boston", "Austin", "Seattle", "Los Angeles"],
    "GBR": ["London", "Cambridge", "Manchester"], "DEU": ["Berlin", "Munich", "Hamburg"],
    "FRA": ["Paris", "Lyon"], "ISR": ["Tel Aviv", "Haifa"],
    "IND": ["Bengaluru", "Mumbai", "Delhi"], "CHN": ["Beijing", "Shanghai", "Shenzhen"],
    "CAN": ["Toronto", "Vancouver"], "SWE": ["Stockholm"], "NLD": ["Amsterdam"],
    "SGP": ["Singapore"], "BRA": ["São Paulo"], "POL": ["Warsaw", "Kraków"],
    "ARE": ["Dubai"], "EST": ["Tallinn"],
}
ROUND_ORDER = ["pre_seed", "seed", "series_a", "series_b", "series_c",
               "series_d", "series_e", "ipo"]
ROUND_SIZE = {
    "pre_seed": (0.15, 0.9), "seed": (0.5, 4.0), "series_a": (3.0, 20.0),
    "series_b": (10.0, 60.0), "series_c": (25.0, 150.0), "series_d": (50.0, 300.0),
    "series_e": (80.0, 500.0), "ipo": (100.0, 1500.0),
}
INV_TYPES = [("vc", .52), ("angel", .21), ("corporate", .14), ("accelerator", .13)]

P1 = ["Nova","Lumen","Vertex","Quanta","Aster","Zenith","Kairo","Orbit","Sable",
      "Helio","Nimbus","Cobalt","Ember","Vireo","Solace","Pylon","Cirrus","Onyx",
      "Vela","Aurum","Kestrel","Lyra","Torus","Mesa","Halcyon","Arbor","Flint"]
P2 = ["Labs","AI","Systems","Works","Health","Pay","Cloud","Data","Robotics","Bio",
      "Tech","Logic","Grid","Flow","Stack","Base","Core","Sense","Loop","Forge"]
IV1 = ["Northline","Blue Harbor","Sequoia Peak","Granite","Foundry","Kite","Meridian",
       "Cascade","Vanta","Redwood Park","Silverline","Highfield","Anchor","Beacon"]
IV2 = ["Capital","Ventures","Partners","Fund","Group","Investments","Equity"]


def pick(pairs):
    r = rnd.random(); acc = 0.0
    for v, w in pairs:
        acc += w
        if r <= acc: return v
    return pairs[-1][0]


def rdate(lo, hi):
    return lo + timedelta(days=rnd.randrange(max(1, (hi - lo).days)))


def fmt(d, style=None):
    if style is None:
        style = rnd.random()
    if style < 0.70:
        return d.isoformat()
    if style < 0.88:
        return d.strftime("%d.%m.%Y")
    return d.strftime("%m/%d/%Y")


def money(v):
    r = rnd.random()
    if r < 0.62:
        return f"{v:.0f}"
    if r < 0.78:
        return f"${v:,.0f}"
    if r < 0.90:
        return f"{v:,.0f}"
    return f"{v/1_000_000:.2f}M"


# ---------------------------------------------------------------- компании
companies, seen = [], set()
for cid in range(1, 8_001):
    for _ in range(80):
        name = f"{rnd.choice(P1)}{rnd.choice(P2)}"
        if name not in seen:
            break
    else:
        name = f"{name}{cid}"
    seen.add(name)
    cat = pick(CATEGORIES)
    country = pick(COUNTRIES)
    city = rnd.choice(CITY_BY_COUNTRY[country]) if country else None
    founded = rdate(START, END - timedelta(days=200))
    status = pick([("operating", .70), ("acquired", .13),
                   ("closed", .13), ("ipo", .04)])
    emp = int(max(1, rnd.lognormvariate(3.1, 1.15)))
    companies.append({
        "company_id": cid, "name": name,
        "category": cat.upper() if rnd.random() < 0.09 else cat,
        "country": country, "city": city,
        "founded_date": founded, "status": status, "employees": emp,
    })

# --------------------------------------------------------------- инвесторы
investors, iseen = [], set()
for iid in range(1, 4_001):
    for _ in range(80):
        name = f"{rnd.choice(IV1)} {rnd.choice(IV2)}"
        if name not in iseen:
            break
    else:
        name = f"{name} {iid}"
    iseen.add(name)
    investors.append([iid, name, pick(COUNTRIES) or "USA", pick(INV_TYPES),
                      rnd.randrange(1985, 2024)])

# ------------------------------------------------------------------ раунды
rounds, investments = [], []
rid = 0
for c in companies:
    # сколько раундов подняла компания
    n = pick([(0, .21), (1, .27), (2, .21), (3, .14), (4, .09), (5, .05), (6, .03)])
    if c["status"] == "closed":
        n = min(n, 2)
    cur = c["founded_date"] + timedelta(days=rnd.randrange(30, 500))
    for step in range(n):
        if step >= len(ROUND_ORDER) - 1 or cur > END:
            break
        rtype = ROUND_ORDER[step]
        lo, hi = ROUND_SIZE[rtype]
        raised = rnd.uniform(lo, hi) * 1_000_000 * rnd.lognormvariate(0, 0.32)
        n_inv = pick([(1, .24), (2, .28), (3, .22), (4, .13), (5, .08), (7, .05)])
        rid += 1
        rounds.append({
            "round_id": rid, "company_id": c["company_id"], "round_type": rtype,
            "announced_date": cur, "raised_usd": raised, "investors_count": n_inv,
        })
        for iid in rnd.sample(range(1, 4001), n_inv):
            investments.append([rid, iid])
        cur = cur + timedelta(days=rnd.randrange(240, 900))
    if c["status"] == "ipo" and cur <= END:
        rid += 1
        raised = rnd.uniform(*ROUND_SIZE["ipo"]) * 1_000_000
        rounds.append({"round_id": rid, "company_id": c["company_id"],
                       "round_type": "ipo", "announced_date": cur,
                       "raised_usd": raised, "investors_count": 1})
        investments.append([rid, rnd.randrange(1, 4001)])

# ------------------------------------------------------------- поглощения
acquisitions = []
acq_id = 0
acquired = [c for c in companies if c["status"] == "acquired"]
big = [c for c in companies if c["status"] in ("operating", "ipo") and c["employees"] > 60]
for c in acquired:
    if rnd.random() < 0.12:      # часть поглощений в выгрузку не попала
        continue
    acq_id += 1
    when = rdate(c["founded_date"] + timedelta(days=400), END)
    price = rnd.lognormvariate(17.2, 1.5)
    acquisitions.append([acq_id, rnd.choice(big)["company_id"], c["company_id"],
                         when, price])

# ------------------------------------------------------------------ грязь
# раунд раньше даты основания
for r in rnd.sample(rounds, 120):
    r["announced_date"] = r["announced_date"] - timedelta(days=rnd.randrange(600, 2500))
# пропуски в employees и country
for c in rnd.sample(companies, int(len(companies) * 0.11)):
    c["employees"] = rnd.choice(["", "n/a", "unknown"])
# задвоенные раунды
next_r = rid + 1
extra = []
for r in rnd.sample(rounds, 180):
    d = dict(r); d["round_id"] = next_r; next_r += 1
    extra.append(d)
rounds += extra
# нулевые и абсурдные суммы
for r in rnd.sample(rounds, 90):
    r["raised_usd"] = rnd.choice([0.0, 1.0, 5e10])

rounds.sort(key=lambda r: r["round_id"])


def dump(name, header, rows):
    path = os.path.join(HERE, name + ".csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    print(f"  {name:14s} {len(rows):>7,} строк, {os.path.getsize(path)/1024:.0f} КБ")


print("Генерация венчурного датасета:")
dump("companies", ["company_id", "name", "category", "country", "city",
                   "founded_date", "status", "employees"],
     [[c["company_id"], c["name"], c["category"], c["country"], c["city"],
       fmt(c["founded_date"]), c["status"], c["employees"]] for c in companies])
dump("rounds", ["round_id", "company_id", "round_type", "announced_date",
                "raised_usd", "investors_count"],
     [[r["round_id"], r["company_id"], r["round_type"], fmt(r["announced_date"]),
       money(r["raised_usd"]), r["investors_count"]] for r in rounds])
dump("investors", ["investor_id", "investor_name", "country", "investor_type",
                   "founded_year"], investors)
dump("investments", ["round_id", "investor_id"], investments)
dump("acquisitions", ["acquisition_id", "acquirer_id", "acquired_id",
                      "announced_date", "price_usd"],
     [[a[0], a[1], a[2], fmt(a[3]), money(a[4])] for a in acquisitions])
print(f"\nГотово: {HERE}")
