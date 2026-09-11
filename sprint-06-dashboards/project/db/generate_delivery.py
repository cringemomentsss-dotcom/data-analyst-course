#!/usr/bin/env python3
"""
Датасет проекта спринта 6: сервис доставки еды «Скороход».

Схема delivery. Данные синтетические, детерминированные.
Запуск: python3 generate_delivery.py  →  CSV в ./out
"""
import csv, os, random
from datetime import datetime, timedelta

rnd = random.Random(60606)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
TS = "%Y-%m-%d %H:%M:%S"
START = datetime(2025, 10, 1)
END = datetime(2026, 6, 30, 23, 59, 59)
DAYS = (END.date() - START.date()).days + 1

CITIES = [
    (1, "Тбилиси", 1.00, .34), (2, "Батуми", 0.78, .16),
    (3, "Кутаиси", 0.71, .13), (4, "Ереван", 0.94, .21),
    (5, "Гюмри", 0.66, .09), (6, "Рустави", 0.68, .07),
]
CUISINES = [("грузинская",.22),("пицца",.17),("суши",.13),("бургеры",.13),
            ("азиатская",.11),("шаурма",.10),("десерты",.08),("здоровая еда",.06)]
VEHICLES = [("велосипед",.31),("скутер",.44),("авто",.17),("пешком",.08)]
PAYMENTS = [("карта",.61),("наличные",.14),("apple_pay",.16),("кошелёк",.09)]
PROMOS = [None]*7 + ["FIRST30","WEEKEND15","FREEDEL","BACK20"]

DISH = ["Хачапури","Хинкали","Пицца Маргарита","Пицца Пепперони","Сет Филадельфия",
        "Сет Калифорния","Чизбургер","Двойной бургер","Пад Тай","Рамен","Шаурма классик",
        "Шаурма острая","Тирамису","Чизкейк","Салат Цезарь","Боул с киноа","Лобио",
        "Оджахури","Харчо","Роллы с лососем","Картофель фри","Лимонад","Кофе латте"]

W1 = ["Старый","Золотой","Синий","Тёплый","Домашний","Городской","Южный","Первый",
      "Дымный","Медный","Белый","Сытный","Ночной","Солнечный","Горный","Речной",
      "Хлебный","Гранатовый","Каменный","Вечерний","Пряный","Зелёный","Красный",
      "Верхний","Нижний","Круглый","Липовый","Ореховый"]
W2 = ["двор","очаг","мангал","стол","квартал","дом","сад","угол","базар","балкон",
      "тандыр","подвал","терраса","рынок","навес","колодец","мост","переулок",
      "фонарь","кувшин","поднос","ковш","чайник","погреб","амбар","сарай",
      "причал","склон"]


def pick(pairs):
    r = rnd.random(); acc = 0.0
    for v, w in pairs:
        acc += w
        if r <= acc: return v
    return pairs[-1][0]


def ts(d): return d.strftime(TS)


# ---- рестораны -----------------------------------------------------------
restaurants = []
seen = set()
for rid in range(1, 861):
    city = pick([(c[0], c[3]) for c in CITIES])
    for _ in range(80):
        name = f"{rnd.choice(W1)} {rnd.choice(W2)}"
        if name not in seen:
            break
    else:
        name = f"{name} №{rid}"
    seen.add(name)
    joined = START - timedelta(days=rnd.randrange(0, 700)) if rnd.random() < 0.7 \
             else START + timedelta(days=rnd.randrange(0, DAYS - 30))
    restaurants.append([rid, name, city, pick(CUISINES),
                        round(rnd.triangular(3.2, 5.0, 4.5), 1),
                        round(rnd.choice([12, 15, 18, 20, 22, 25]) + rnd.uniform(-1, 1), 1),
                        joined.date().isoformat()])
rest_city = {r[0]: r[2] for r in restaurants}
w = sorted((rnd.paretovariate(1.4) for _ in restaurants), reverse=True)
_by_city = {}
for r, x in zip(restaurants, w):
    _by_city.setdefault(r[2], []).append((r[0], x))
# нормируем внутри каждого города
REST_BY_CITY = {}
for city, lst in _by_city.items():
    tot = sum(x for _, x in lst)
    REST_BY_CITY[city] = [(rid, x / tot) for rid, x in lst]

# ---- курьеры -------------------------------------------------------------
couriers = []
for cid in range(1, 1_101):
    city = pick([(c[0], c[3]) for c in CITIES])
    hired = START - timedelta(days=rnd.randrange(0, 500)) if rnd.random() < 0.55 \
            else START + timedelta(days=rnd.randrange(0, DAYS - 20))
    term = None
    if rnd.random() < 0.29:
        t = max(hired, START) + timedelta(days=rnd.randrange(30, 260))
        if t <= END: term = t
    couriers.append([cid, city, pick(VEHICLES), hired.date().isoformat(),
                     term.date().isoformat() if term else None])
cour_by_city = {}
for c in couriers:
    cour_by_city.setdefault(c[1], []).append(c)

# ---- клиенты -------------------------------------------------------------
customers = []
for uid in range(1, 38_001):
    city = pick([(c[0], c[3]) for c in CITIES])
    signup = START + timedelta(days=int(rnd.random() ** 1.35 * DAYS))
    customers.append([uid, city, signup.date().isoformat(),
                      pick([("ios",.42),("android",.46),("web",.12)])])
cust_city = {c[0]: c[1] for c in customers}
cust_signup = {c[0]: datetime.fromisoformat(c[2]) for c in customers}

# частота заказов: тяжёлый хвост
freq = {}
for c in customers:
    freq[c[0]] = max(1, min(int(rnd.paretovariate(1.15)), 120))

# ---- заказы --------------------------------------------------------------
orders, items = [], []
oid = 0
for c in customers:
    uid = c[0]
    su = cust_signup[uid]
    span = (END - su).days
    if span <= 0:
        continue
    for _ in range(freq[uid]):
        created = su + timedelta(days=int(rnd.random() ** 1.25 * span),
                                 hours=rnd.choices(range(24), weights=[
                                     1,1,1,1,1,1,2,3,4,6,8,12,16,12,8,7,9,14,18,16,11,7,4,2])[0],
                                 minutes=rnd.randrange(60), seconds=rnd.randrange(60))
        if created > END:
            continue
        rid = pick(REST_BY_CITY[cust_city[uid]])

        pool = cour_by_city.get(cust_city[uid], [])
        courier = rnd.choice(pool)[0] if pool and rnd.random() > 0.03 else None

        status = pick([("delivered",.918),("cancelled_by_user",.041),
                       ("cancelled_by_restaurant",.026),("cancelled_by_courier",.015)])
        city_mult = next(cc[2] for cc in CITIES if cc[0] == cust_city[uid])

        n_items = pick([(1,.27),(2,.31),(3,.21),(4,.12),(5,.06),(6,.03)])
        items_total = 0.0
        basket = []
        for _ in range(n_items):
            dish = rnd.choice(DISH)
            qty = pick([(1,.78),(2,.16),(3,.06)])
            price = round(rnd.uniform(6, 34) * city_mult, 2)
            basket.append((dish, qty, price))
            items_total += qty * price
        items_total = round(items_total, 2)

        delivery_fee = round(rnd.choice([0, 1.5, 2.0, 2.5, 3.0]) * city_mult, 2)
        promo = rnd.choice(PROMOS)
        discount = 0.0
        if promo:
            discount = round(items_total * rnd.choice([.10, .15, .20, .30]), 2)

        accepted = created + timedelta(seconds=rnd.randrange(20, 480))
        prep = int(max(240, rnd.gauss(1020, 380)))
        picked = accepted + timedelta(seconds=prep)
        ride = int(max(180, rnd.gauss(1080, 460)))
        delivered = picked + timedelta(seconds=ride)

        oid += 1
        if status == "delivered":
            row = [oid, uid, rid, courier, ts(created), ts(accepted), ts(picked),
                   ts(delivered), None, status, items_total, delivery_fee, discount,
                   promo, pick(PAYMENTS),
                   pick([(5,.58),(4,.21),(3,.09),(2,.05),(1,.07)]) if rnd.random() < 0.42 else None]
        else:
            cancelled = created + timedelta(seconds=rnd.randrange(30, 1800))
            row = [oid, uid, rid, courier if status != "cancelled_by_user" else None,
                   ts(created),
                   ts(accepted) if status != "cancelled_by_user" else None,
                   None, None, ts(cancelled), status, items_total, delivery_fee,
                   discount, promo, pick(PAYMENTS), None]
        orders.append(row)
        for dish, qty, price in basket:
            items.append([oid, dish, qty, price])

# ---- грязь ---------------------------------------------------------------
# отменённые заказы, у которых почему-то заполнено время доставки
for r in rnd.sample([r for r in orders if r[9] != "delivered"], 120):
    r[7] = ts(datetime.strptime(r[4], TS) + timedelta(seconds=rnd.randrange(900, 4000)))
# время доставки раньше времени создания
for r in rnd.sample([r for r in orders if r[9] == "delivered"], 90):
    r[7] = ts(datetime.strptime(r[4], TS) - timedelta(minutes=rnd.randrange(5, 120)))
# «зависшие» заказы: курьер не нажал кнопку, статус закрылся автоматически
# ночью. Их около процента, но среднее время доставки они ломают полностью.
for r in rnd.sample([r for r in orders if r[9] == "delivered"], 1400):
    r[7] = ts(datetime.strptime(r[6], TS) + timedelta(hours=rnd.randrange(6, 60)))
# задвоенные заказы
items_by_order = {}
for it in items:
    items_by_order.setdefault(it[0], []).append(it)
dupes = []
for r in rnd.sample(orders, 260):
    d = list(r); oid += 1; d[0] = oid
    dupes.append(d)
    for it in items_by_order.get(r[0], []):
        items.append([d[0], it[1], it[2], it[3]])
orders += dupes
# нулевая сумма заказа
for r in rnd.sample(orders, 70):
    r[10] = 0.0

orders.sort(key=lambda r: r[4])
items.sort(key=lambda r: r[0])


def dump(name, header, rows):
    with open(os.path.join(OUT, name + ".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    print(f"  {name:14s} {len(rows):>9,}")


print("Генерация «Скорохода»:")
dump("cities", ["city_id", "city", "price_index"],
     [[c[0], c[1], c[2]] for c in CITIES])
dump("restaurants", ["restaurant_id", "restaurant_name", "city_id", "cuisine",
                     "rating", "commission_pct", "joined_date"], restaurants)
dump("couriers", ["courier_id", "city_id", "vehicle", "hired_date", "terminated_date"], couriers)
dump("customers", ["customer_id", "city_id", "signup_date", "platform"], customers)
dump("orders", ["order_id", "customer_id", "restaurant_id", "courier_id", "created_at",
                "accepted_at", "picked_at", "delivered_at", "cancelled_at", "status",
                "items_total", "delivery_fee", "discount", "promo_code",
                "payment_method", "rating"], orders)
dump("order_items", ["order_id", "item_name", "qty", "price"], items)
print(f"\nГотово: {OUT}")
