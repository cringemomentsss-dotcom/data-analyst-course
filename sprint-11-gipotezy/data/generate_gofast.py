#!/usr/bin/env python3
"""
Датасет проекта спринта 11: сервис проката самокатов GoFast.

Три файла: пользователи, поездки, тарифы.
Запуск: python3 generate_gofast.py
"""
import csv, os, random
from datetime import date, timedelta

rnd = random.Random(1111)
HERE = os.path.dirname(os.path.abspath(__file__))
START = date(2025, 5, 1)
END = date(2026, 6, 30)
DAYS = (END - START).days + 1

CITIES = [
    ("Тбилиси", .22), ("Батуми", .14), ("Ереван", .18), ("Кутаиси", .09),
    ("Гюмри", .07), ("Рустави", .08), ("Поти", .10), ("Ванадзор", .12),
]

# Тарифы: подписка ultra — минута дешевле, старт бесплатный, есть абонплата
TARIFFS = [
    ("free", 8.0, 50.0, 0.0),
    ("ultra", 6.0, 0.0, 199.0),
]


def pick(pairs):
    r = rnd.random(); acc = 0.0
    for v, w in pairs:
        acc += w
        if r <= acc: return v
    return pairs[-1][0]


# ------------------------------------------------------------ пользователи
users = []
for uid in range(1, 1_501):
    sub = pick([("free", .58), ("ultra", .42)])
    age = int(min(58, max(12, rnd.gauss(27.5, 8.2))))
    users.append([uid, age, pick(CITIES), sub])
sub_of = {u[0]: u[3] for u in users}

# ------------------------------------------------------------------ поездки
rides = []
rid = 0
for u in users:
    uid, age, city, sub = u
    # у подписчиков поездок больше
    n = int(max(1, rnd.gauss(22 if sub == "ultra" else 9,
                             9 if sub == "ultra" else 5)))
    for _ in range(n):
        d = START + timedelta(days=rnd.randrange(DAYS))
        # длительность: у подписчиков чуть больше; логнормальная форма
        if sub == "ultra":
            dur = rnd.lognormvariate(2.86, 0.44)     # медиана ~17.5 мин
        else:
            dur = rnd.lognormvariate(2.75, 0.46)     # медиана ~15.6 мин
        dur = round(min(90.0, max(0.5, dur)), 2)
        # расстояние коррелирует с длительностью через скорость
        speed = rnd.gauss(156, 34)                    # метров в минуту
        dist = round(max(50.0, dur * max(60, speed)), 1)
        rid += 1
        rides.append([rid, uid, dist, dur, d.isoformat()])

# ---------------------------------------------------------------- грязь
# несколько поездок нулевой длительности — самокат не разблокировался
for r in rnd.sample(rides, 90):
    r[3] = 0.0
    r[2] = 0.0
# пропущенный возраст у части пользователей
for u in rnd.sample(users, 62):
    u[1] = ""
# задвоенные поездки
next_r = rid + 1
extra = []
for r in rnd.sample(rides, 140):
    d = list(r); d[0] = next_r; next_r += 1
    extra.append(d)
rides += extra
rides.sort(key=lambda r: (r[4], r[0]))


def dump(name, header, rows):
    path = os.path.join(HERE, name + ".csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    print(f"  {name:16s} {len(rows):>7,} строк, {os.path.getsize(path)/1024:.0f} КБ")


print("Генерация GoFast:")
dump("users", ["user_id", "age", "city", "subscription_type"], users)
dump("rides", ["ride_id", "user_id", "distance_m", "duration_min", "ride_date"], rides)
dump("tariffs", ["subscription_type", "minute_price", "start_price",
                 "subscription_fee"], TARIFFS)
print(f"\nГотово: {HERE}")
