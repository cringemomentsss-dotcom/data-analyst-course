#!/usr/bin/env python3
"""
Датасет итогового проекта модуля 1: объявления о продаже жилья.

Схема estate. Одна широкая таблица с пропусками, выбросами и мусором —
ровно так выглядит выгрузка из классифайда.

Запуск: python3 generate_estate.py  →  CSV в ./out
"""
import csv, os, random
from datetime import datetime, timedelta

rnd = random.Random(2026)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
START = datetime(2024, 11, 1)
END = datetime(2026, 5, 31)
DAYS = (END.date() - START.date()).days + 1

# id, название, тип, население, множитель цены за м², расстояние до центра региона
LOCALITIES = [
    (1,  "Санкт-Петербург",        "город",   5_600_000, 1.00,      0),
    (2,  "Мурино",                 "посёлок",    95_000, 0.62,  22_000),
    (3,  "Кудрово",                "посёлок",    55_000, 0.66,  17_000),
    (4,  "Шушары",                 "посёлок",    40_000, 0.58,  20_000),
    (5,  "Всеволожск",             "город",      75_000, 0.55,  26_000),
    (6,  "Пушкин",                 "город",      110_000, 0.71, 28_000),
    (7,  "Колпино",                "город",      145_000, 0.53, 30_000),
    (8,  "Парголово",              "посёлок",    28_000, 0.64,  18_000),
    (9,  "Гатчина",                "город",      95_000, 0.46,  45_000),
    (10, "Выборг",                 "город",      75_000, 0.38, 120_000),
    (11, "Петергоф",               "город",      85_000, 0.60,  32_000),
    (12, "Сестрорецк",             "город",      42_000, 0.68,  34_000),
    (13, "Красное Село",           "город",      60_000, 0.50,  27_000),
    (14, "Сертолово",              "город",      55_000, 0.52,  24_000),
    (15, "Никольское",             "город",      22_000, 0.40,  40_000),
]
LOC_W = [(l[0], w) for l, w in zip(LOCALITIES, [
    .43,.075,.062,.038,.045,.035,.040,.028,.032,.028,.026,.020,.030,.027,.014])]

BASE_M2 = 168_000   # рублей за м² в центре Петербурга


def pick(pairs):
    r = rnd.random(); acc = 0.0
    for v, w in pairs:
        acc += w
        if r <= acc: return v
    return pairs[-1][0]


def maybe(value, p_missing):
    return None if rnd.random() < p_missing else value


rows = []
for lid in range(1, 23_001):
    loc = pick(LOC_W)
    _, _, _, _, mult, dist_base = next(l for l in LOCALITIES if l[0] == loc)

    rooms = pick([(0, .04), (1, .33), (2, .32), (3, .22), (4, .06), (5, .025), (6, .005)])
    is_studio = 1 if rooms == 0 else 0
    is_open_plan = 1 if (rooms == 0 and rnd.random() < 0.22) else 0
    is_apartment = 1 if rnd.random() < 0.021 else 0

    base_area = {0: 26, 1: 37, 2: 55, 3: 76, 4: 103, 5: 132, 6: 168}[rooms]
    area_total = round(max(12.0, rnd.gauss(base_area, base_area * 0.17)), 1)
    area_living = round(area_total * rnd.uniform(0.42, 0.63), 1)
    area_kitchen = round(area_total * rnd.uniform(0.11, 0.22), 1) if rooms else None

    floors_total = pick([(5, .21), (9, .24), (12, .13), (16, .12), (17, .07),
                         (18, .06), (22, .06), (25, .07), (4, .04)])
    floor = rnd.randint(1, floors_total)
    ceiling = round(rnd.choice([2.5, 2.55, 2.6, 2.65, 2.7, 2.75, 2.8, 3.0, 3.2]), 2)

    centers = int(max(300, rnd.gauss(dist_base + (8000 if loc == 1 else 3000),
                                     4200 if loc == 1 else 1800)))
    airports = int(max(2000, rnd.gauss(24_000 + centers * 0.55, 9_000)))
    parks_around = pick([(0, .44), (1, .29), (2, .18), (3, .09)])
    parks_nearest = int(rnd.gauss(520, 210)) if parks_around else None
    ponds_around = pick([(0, .49), (1, .27), (2, .17), (3, .07)])
    ponds_nearest = int(rnd.gauss(560, 240)) if ponds_around else None

    # цена: площадь × ставка × поправки
    rate = BASE_M2 * mult
    rate *= 1 + 0.10 * (1 if floor not in (1, floors_total) else -1) * 0.5
    rate *= 1 + (0.06 if parks_around else 0)
    rate *= 1 + (0.05 if ceiling >= 3.0 else 0)
    rate *= max(0.72, 1.18 - centers / 90_000)
    rate *= rnd.lognormvariate(0, 0.13)
    price = round(area_total * rate, -3)

    posted = START + timedelta(days=rnd.randrange(DAYS))
    # срок экспозиции: длинный хвост
    expo = int(min(rnd.lognormvariate(4.35, 0.95), 1200))
    removed = posted + timedelta(days=expo)
    sold = removed <= END
    balconies = pick([(0, .46), (1, .34), (2, .17), (3, .03)])
    images = pick([(0, .06), (5, .18), (8, .21), (10, .19), (12, .16), (15, .12), (20, .08)])

    rows.append([
        lid, posted.date().isoformat(),
        removed.date().isoformat() if sold else None,
        expo if sold else None,
        loc, price, rooms, area_total,
        maybe(area_living, 0.08),
        maybe(area_kitchen, 0.10) if area_kitchen else None,
        maybe(ceiling, 0.39),
        floor, floors_total, is_apartment, is_studio, is_open_plan,
        maybe(balconies, 0.48),
        maybe(airports, 0.24), maybe(centers, 0.22),
        parks_around, maybe(parks_nearest, 0.05) if parks_nearest else None,
        ponds_around, maybe(ponds_nearest, 0.05) if ponds_nearest else None,
        images,
    ])

# ---- мусор ---------------------------------------------------------------
def col(i): return i

# потолки-выбросы: метры перепутаны с сантиметрами и просто опечатки
for r in rnd.sample([r for r in rows if r[10] is not None], 140):
    r[10] = rnd.choice([1.0, 1.2, 14.0, 20.0, 24.0, 25.0, 27.0, 32.0, 100.0])
# нулевые и абсурдные цены
for r in rnd.sample(rows, 60):
    r[5] = rnd.choice([12190.0, 1.0, 763_000_000.0, 420_000_000.0])
# площади-выбросы
for r in rnd.sample(rows, 55):
    r[7] = rnd.choice([900.0, 631.2, 12.0, 8.0])
# этаж больше этажности дома
for r in rnd.sample(rows, 90):
    r[11] = r[12] + rnd.randint(1, 4)
# жилая площадь больше общей
for r in rnd.sample([r for r in rows if r[8] is not None], 70):
    r[8] = round(r[7] * rnd.uniform(1.05, 1.6), 1)
# задвоенные объявления
extra = []
next_id = len(rows) + 1
for r in rnd.sample(rows, 190):
    d = list(r); d[0] = next_id; next_id += 1
    extra.append(d)
rows += extra
rows.sort(key=lambda r: (r[1], r[0]))

HEADER = ["listing_id", "posted_date", "removed_date", "days_exposition",
          "locality_id", "price_rub", "rooms", "area_total", "area_living",
          "area_kitchen", "ceiling_height", "floor", "floors_total",
          "is_apartment", "is_studio", "is_open_plan", "balconies",
          "airport_dist_m", "center_dist_m", "parks_around_3000",
          "park_nearest_m", "ponds_around_3000", "pond_nearest_m", "images_count"]


def dump(name, header, data):
    with open(os.path.join(OUT, name + ".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(data)
    print(f"  {name:14s} {len(data):>8,}")


# в справочнике намеренно два написания типа населённого пункта
loc_rows = []
for i, name, kind, pop, mult, dist in LOCALITIES:
    if kind == "посёлок" and rnd.random() < 0.5:
        kind = "поселок"
    loc_rows.append([i, name, kind, pop])

print("Генерация рынка недвижимости:")
dump("localities", ["locality_id", "locality_name", "locality_type", "population"], loc_rows)
dump("listings", HEADER, rows)
print(f"\nГотово: {OUT}")
