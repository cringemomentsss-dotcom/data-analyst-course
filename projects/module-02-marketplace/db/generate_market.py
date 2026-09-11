#!/usr/bin/env python3
"""
Датасет итогового проекта модуля 2: маркетплейс «Полка».

Схема market. Данные синтетические, детерминированные.
Запуск: python3 generate_market.py  →  CSV в ./out
"""
import bisect
import csv, os, random
from datetime import datetime, timedelta

rnd = random.Random(20262)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
TS = "%Y-%m-%d %H:%M:%S"
START = datetime(2025, 7, 1)
END = datetime(2026, 6, 30, 23, 59, 59)
DAYS = (END.date() - START.date()).days + 1


def pick(pairs):
    r = rnd.random(); acc = 0.0
    for v, w in pairs:
        acc += w
        if r <= acc: return v
    return pairs[-1][0]


def ts(d): return d.strftime(TS)


# ---- категории: три уровня ------------------------------------------------
TREE = {
    "Электроника": {
        "Смартфоны": ["Android", "iPhone", "Кнопочные"],
        "Ноутбуки": ["Ультрабуки", "Игровые", "Рабочие"],
        "Аудио": ["Наушники", "Колонки", "Микрофоны"],
    },
    "Дом": {
        "Кухня": ["Посуда", "Техника для кухни", "Хранение"],
        "Текстиль": ["Постельное", "Шторы", "Полотенца"],
        "Мебель": ["Стулья", "Столы", "Полки"],
    },
    "Одежда": {
        "Верхняя": ["Куртки", "Пальто"],
        "Обувь": ["Кроссовки", "Ботинки", "Сандалии"],
        "Базовое": ["Футболки", "Джинсы", "Свитеры"],
    },
    "Красота": {
        "Уход": ["Лицо", "Тело", "Волосы"],
        "Косметика": ["Глаза", "Губы", "Тон"],
    },
    "Спорт": {
        "Тренировки": ["Гантели", "Коврики", "Эспандеры"],
        "Активности": ["Велосипеды", "Самокаты", "Туризм"],
    },
    "Детям": {
        "Игрушки": ["Конструкторы", "Мягкие", "Настольные"],
        "Одежда детская": ["До года", "Дошкольники"],
    },
}
PRICE_BAND = {
    "Смартфоны": (180, 1400), "Ноутбуки": (400, 2600), "Аудио": (15, 420),
    "Кухня": (8, 320), "Текстиль": (10, 160), "Мебель": (35, 700),
    "Верхняя": (45, 480), "Обувь": (30, 290), "Базовое": (9, 90),
    "Уход": (6, 120), "Косметика": (5, 95),
    "Тренировки": (10, 260), "Активности": (60, 1200),
    "Игрушки": (7, 180), "Одежда детская": (8, 70),
}

categories = []
cat_id = 0
leaf_ids = []          # (leaf_id, l2_name)
for l1, subs in TREE.items():
    cat_id += 1; l1_id = cat_id
    categories.append([l1_id, l1, None, 1])
    for l2, leaves in subs.items():
        cat_id += 1; l2_id = cat_id
        categories.append([l2_id, l2, l1_id, 2])
        for leaf in leaves:
            cat_id += 1
            categories.append([cat_id, leaf, l2_id, 3])
            leaf_ids.append((cat_id, l2))

# ---- продавцы ------------------------------------------------------------
SELLER_A = ["Альфа","Бета","Гамма","Дельта","Нова","Прайм","Верде","Соларис","Кобальт",
            "Мираж","Титан","Ясень","Кедр","Гранат","Лотос","Оникс","Веста","Сириус"]
SELLER_B = ["Трейд","Стор","Шоп","Групп","Маркет","Хаус","Лайн","Сити","Плюс","Про",
            "Дистрибьюшн","Импорт","Ритейл","Логистик"]
SELLER_COUNTRIES = [("GE",.28),("AM",.19),("TR",.17),("PL",.12),("DE",.09),
                    ("CN",.08),("KZ",.07)]

sellers = []
seen = set()
for sid in range(1, 2_001):
    for _ in range(80):
        name = f"{rnd.choice(SELLER_A)} {rnd.choice(SELLER_B)}"
        if name not in seen:
            break
    else:
        name = f"{name} {sid}"
    seen.add(name)
    joined = START - timedelta(days=rnd.randrange(0, 900)) if rnd.random() < 0.6 \
             else START + timedelta(days=rnd.randrange(0, DAYS - 40))
    sellers.append([sid, name, pick(SELLER_COUNTRIES), joined.date().isoformat(),
                    pick([("basic",.62),("plus",.27),("premium",.11)])])
seller_tier = {s[0]: s[4] for s in sellers}
COMMISSION = {"basic": 17.0, "plus": 13.5, "premium": 10.0}

# ---- товары --------------------------------------------------------------
ADJ = ["классический","компактный","премиальный","базовый","лёгкий","прочный",
       "беспроводной","складной","утеплённый","минималистичный","профессиональный"]
products = []
for pid in range(1, 25_001):
    leaf, l2 = rnd.choice(leaf_ids)
    lo, hi = PRICE_BAND[l2]
    price = round(rnd.uniform(lo, hi) * rnd.lognormvariate(0, 0.22), 2)
    listed = START - timedelta(days=rnd.randrange(0, 600)) if rnd.random() < 0.5 \
             else START + timedelta(days=rnd.randrange(0, DAYS - 10))
    products.append([pid, rnd.randrange(1, 2001), leaf,
                     f"{l2} {rnd.choice(ADJ)}", price,
                     listed.date().isoformat(),
                     1 if rnd.random() < 0.87 else 0])
prod_seller = {p[0]: p[1] for p in products}
prod_price = {p[0]: p[4] for p in products}
prod_cat = {p[0]: p[2] for p in products}

# Популярность товаров — длинный хвост. Выбор через накопленные веса и
# бинарный поиск: линейный проход по 25 тысячам товаров на каждую позицию
# заказа делал генерацию в двадцать раз медленнее.
w = sorted((rnd.paretovariate(1.35) for _ in products), reverse=True)
PROD_IDS = [p[0] for p in products]
PROD_CUM = []
acc = 0.0
for x in w:
    acc += x
    PROD_CUM.append(acc)
PROD_TOTAL = acc


def pick_product():
    return PROD_IDS[bisect.bisect_left(PROD_CUM, rnd.random() * PROD_TOTAL)]

# ---- покупатели ----------------------------------------------------------
BUYER_COUNTRIES = [("GE",.31),("AM",.24),("TR",.14),("KZ",.11),("PL",.09),
                   ("DE",.06),(None,.05)]
CHANNELS = [("organic",.24),("paid_search",.21),("social",.19),("email",.13),
            ("affiliate",.12),("direct",.11)]
buyers = []
for bid in range(1, 80_001):
    su = START + timedelta(days=int(rnd.random() ** 1.3 * DAYS))
    buyers.append([bid, pick(BUYER_COUNTRIES), su.date().isoformat(), pick(CHANNELS)])
buyer_signup = {b[0]: datetime.fromisoformat(b[2]) for b in buyers}

freq = {b[0]: max(1, min(int(rnd.paretovariate(1.25)), 60)) for b in buyers}

# ---- заказы --------------------------------------------------------------
PAYMENTS = [("card",.66),("apple_pay",.14),("wallet",.11),("cash_on_delivery",.09)]
PROMOS = [None]*8 + ["NEW10","SALE20","SHIPFREE"]

orders, lines, returns_, reviews = [], [], [], []
oid = 0
rid_ret = 0
rid_rev = 0
RETURN_REASONS = [("не подошёл размер",.31),("брак",.22),("не соответствует описанию",.19),
                  ("передумал",.16),("повреждено при доставке",.12)]

for b in buyers:
    bid = b[0]
    su = buyer_signup[bid]
    span = (END - su).days
    if span <= 0:
        continue
    for _ in range(freq[bid]):
        created = su + timedelta(days=int(rnd.random() ** 1.2 * span),
                                 hours=rnd.choices(range(24), weights=[
                                     2,1,1,1,1,1,2,4,6,7,8,8,8,8,8,8,9,10,11,10,8,6,4,3])[0],
                                 minutes=rnd.randrange(60))
        if created > END:
            continue
        oid += 1
        status = pick([("delivered",.869),("cancelled",.058),("returned",.043),("in_transit",.030)])
        n_lines = pick([(1,.61),(2,.24),(3,.10),(4,.05)])
        chosen = set()
        for _ in range(n_lines):
            chosen.add(pick_product())
        promo = rnd.choice(PROMOS)
        shipping = round(rnd.choice([0, 2, 3, 4.5]) * rnd.uniform(.9, 1.1), 2)
        orders.append([oid, bid, ts(created), status, pick(PAYMENTS),
                       b[1] or pick([(c, w) for c, w in BUYER_COUNTRIES if c]),
                       promo, shipping])
        for p in chosen:
            qty = pick([(1,.82),(2,.13),(3,.05)])
            price = round(prod_price[p] * rnd.uniform(.92, 1.06), 2)
            sid = prod_seller[p]
            lines.append([oid, p, sid, qty, price, COMMISSION[seller_tier[sid]]])
            # возвраты
            if status == "returned" or (status == "delivered" and rnd.random() < 0.018):
                rid_ret += 1
                rday = created + timedelta(days=rnd.randrange(3, 30))
                if rday <= END:
                    returns_.append([rid_ret, oid, p, ts(rday),
                                     pick(RETURN_REASONS), round(price * qty, 2)])
            # отзывы
            if status == "delivered" and rnd.random() < 0.21:
                rid_rev += 1
                rvday = created + timedelta(days=rnd.randrange(2, 45))
                if rvday <= END:
                    reviews.append([rid_rev, p, bid, ts(rvday),
                                    pick([(5,.54),(4,.22),(3,.10),(2,.06),(1,.08)]),
                                    1 if rnd.random() < 0.63 else 0])

# ---- грязь ---------------------------------------------------------------
# отменённые заказы, у которых остались позиции — норма, но их надо исключать из выручки
# задвоенные отзывы: один покупатель, один товар, одна дата
for r in rnd.sample(reviews, int(len(reviews) * 0.011)):
    rid_rev += 1
    reviews.append([rid_rev] + r[1:])
# несколько возвратов на сумму больше стоимости позиции
for r in rnd.sample(returns_, 90):
    r[5] = round(r[5] * rnd.uniform(1.5, 3.0), 2)
# страна доставки не заполнена
for o in rnd.sample(orders, int(len(orders) * 0.014)):
    o[5] = None

orders.sort(key=lambda r: r[2])
lines.sort(key=lambda r: r[0])
returns_.sort(key=lambda r: r[3])
reviews.sort(key=lambda r: r[3])


def dump(name, header, rows):
    with open(os.path.join(OUT, name + ".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    print(f"  {name:14s} {len(rows):>9,}")


print("Генерация «Полки»:")
dump("categories", ["category_id", "category_name", "parent_id", "level"], categories)
dump("sellers", ["seller_id", "seller_name", "country", "joined_date", "tier"], sellers)
dump("products", ["product_id", "seller_id", "category_id", "title", "price",
                  "listed_date", "is_active"], products)
dump("buyers", ["buyer_id", "country", "signup_date", "channel"], buyers)
dump("orders", ["order_id", "buyer_id", "created_at", "status", "payment_method",
                "delivery_country", "promo_code", "shipping_cost"], orders)
dump("order_lines", ["order_id", "product_id", "seller_id", "qty", "price",
                     "commission_pct"], lines)
dump("returns", ["return_id", "order_id", "product_id", "created_at", "reason",
                 "refund_amount"], returns_)
dump("reviews", ["review_id", "product_id", "buyer_id", "created_at", "rating",
                 "has_text"], reviews)
print(f"\nГотово: {OUT}")
