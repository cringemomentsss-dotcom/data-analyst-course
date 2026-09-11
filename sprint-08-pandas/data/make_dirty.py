#!/usr/bin/env python3
"""
Готовит грязные выгрузки для проекта спринта 8.

Берёт чистые данные из схемы game (нужен поднятый `make game`) и портит их
так, как портятся настоящие выгрузки: смешанные форматы дат, числа строками,
пропуски пятью разными способами, дубликаты, неконсистентные категории.

Запуск: python3 make_dirty.py
Результат: igroki.csv, pokupki.csv
"""
import csv
import io
import os
import random
import subprocess
import sys

rnd = random.Random(808)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def query(sql):
    p = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql",
         "-U", "analyst", "-d", "casino", "-v", "ON_ERROR_STOP=1", "-q", "--csv"],
        input=sql, capture_output=True, text=True, cwd=ROOT)
    if p.returncode != 0:
        sys.exit("Ошибка SQL. Схема game поднята? Запусти `make game`.\n" + p.stderr)
    return list(csv.DictReader(io.StringIO(p.stdout)))


MISSING = ["", "", "", "NaN", "null", "-", "н/д"]


def blank():
    return rnd.choice(MISSING)


# ---------------------------------------------------------------- игроки
players = query("""
SET search_path TO game;
SELECT p.player_id, p.reg_date, p.country, p.platform, p.channel,
       count(s.session_id) AS sessions,
       coalesce(round(sum(s.duration_min)::numeric, 1), 0) AS total_minutes,
       coalesce(max(s.level_end), 1) AS max_level
FROM players p LEFT JOIN sessions s USING (player_id)
GROUP BY p.player_id, p.reg_date, p.country, p.platform, p.channel
ORDER BY p.player_id;
""")

COUNTRY_VARIANTS = {
    "DE": ["DE", "de", "Germany", "GER"],
    "US": ["US", "us", "USA"],
    "BR": ["BR", "br", "Brazil"],
    "RU": ["RU", "ru", "Russia"],
    "TR": ["TR", "tr", "Turkey"],
}
PLATFORM_VARIANTS = {
    "ios": ["ios", "iOS", "IOS"],
    "android": ["android", "Android", "ANDROID"],
    "pc": ["pc", "PC", "Windows"],
}

pl_rows = []
for r in players:
    country = r["country"]
    if not country:
        country = blank()
    elif country in COUNTRY_VARIANTS and rnd.random() < 0.22:
        country = rnd.choice(COUNTRY_VARIANTS[country])
    platform = rnd.choice(PLATFORM_VARIANTS[r["platform"]]) if rnd.random() < 0.3 else r["platform"]
    # дата регистрации в двух форматах
    d = r["reg_date"]
    if rnd.random() < 0.28:
        y, m, dd = d.split("-")
        d = f"{dd}.{m}.{y}"
    minutes = r["total_minutes"]
    if rnd.random() < 0.06:
        minutes = blank()
    elif rnd.random() < 0.05:
        minutes = str(minutes).replace(".", ",")
    pl_rows.append([r["player_id"], d, country, platform, r["channel"],
                    r["sessions"], minutes, r["max_level"]])

# несколько отрицательных значений минут — баг клиента
for r in rnd.sample([x for x in pl_rows if isinstance(x[6], str) and x[6] not in MISSING], 40):
    r[6] = "-" + str(r[6])

# задвоенные игроки: та же строка с другим player_id
dupes = []
next_id = max(int(r[0]) for r in pl_rows) + 1
for r in rnd.sample(pl_rows, 130):
    d = list(r)
    d[0] = next_id
    next_id += 1
    dupes.append(d)
pl_rows += dupes

# ---------------------------------------------------------------- покупки
purchases = query("""
SET search_path TO game;
SELECT pu.purchase_id, pu.player_id, i.item_name, i.category, i.rarity,
       pu.purchase_ts, pu.price_paid, coalesce(pu.promo_code, '') AS promo_code,
       pu.status
FROM purchases pu JOIN items i USING (item_id)
ORDER BY pu.purchase_id;
""")

pu_rows = []
for r in purchases:
    price = r["price_paid"]
    roll = rnd.random()
    if roll < 0.09:
        price = f"{price} USD"
    elif roll < 0.16:
        price = str(price).replace(".", ",")
    elif roll < 0.18:
        price = blank()
    ts = r["purchase_ts"]
    if rnd.random() < 0.24:
        date_part, time_part = ts.split(" ")
        y, m, d = date_part.split("-")
        ts = f"{d}.{m}.{y} {time_part}"
    rarity = r["rarity"].upper() if rnd.random() < 0.18 else r["rarity"]
    promo = r["promo_code"] or blank()
    pu_rows.append([r["purchase_id"], r["player_id"], r["item_name"],
                    r["category"], rarity, ts, price, promo, r["status"]])

# задвоенные покупки
next_pu = max(int(r[0]) for r in pu_rows) + 1
extra = []
for r in rnd.sample(pu_rows, 90):
    d = list(r)
    d[0] = next_pu
    next_pu += 1
    extra.append(d)
pu_rows += extra

rnd.shuffle(pu_rows)
pu_rows.sort(key=lambda r: int(r[0]))


def dump(name, header, rows):
    path = os.path.join(HERE, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  {name:14s} {len(rows):>7,} строк, {os.path.getsize(path)/1024:.0f} КБ")


print("Грязные выгрузки «Секретов Темнолесья»:")
dump("igroki.csv", ["player_id", "reg_date", "country", "platform", "channel",
                    "sessions", "total_minutes", "max_level"], pl_rows)
dump("pokupki.csv", ["purchase_id", "player_id", "item_name", "category", "rarity",
                     "purchase_ts", "price_paid", "promo_code", "status"], pu_rows)
print(f"\nГотово: {HERE}")
