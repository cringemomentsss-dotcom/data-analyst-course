#!/usr/bin/env python3
"""
Датасет проекта спринта 9: рынок общественного питания Москвы.

Один широкий файл — как выгрузка из справочника заведений.
Запуск: python3 generate_food.py  →  zavedeniya.csv
"""
import csv, os, random

rnd = random.Random(909)
HERE = os.path.dirname(os.path.abspath(__file__))

# район, округ, множитель аренды/чека, доля заведений
DISTRICTS = [
    ("Арбат", "ЦАО", 1.85, .030), ("Тверской", "ЦАО", 1.90, .042),
    ("Хамовники", "ЦАО", 1.70, .034), ("Замоскворечье", "ЦАО", 1.65, .028),
    ("Басманный", "ЦАО", 1.55, .038), ("Пресненский", "ЦАО", 1.80, .036),
    ("Мещанский", "ЦАО", 1.45, .022), ("Таганский", "ЦАО", 1.40, .030),
    ("Даниловский", "ЮАО", 1.05, .026), ("Донской", "ЮАО", 1.00, .020),
    ("Академический", "ЮЗАО", 1.00, .024), ("Гагаринский", "ЮЗАО", 1.10, .020),
    ("Раменки", "ЗАО", 1.05, .028), ("Дорогомилово", "ЗАО", 1.25, .022),
    ("Сокол", "САО", 1.10, .020), ("Аэропорт", "САО", 1.05, .022),
    ("Бутырский", "СВАО", 0.85, .024), ("Отрадное", "СВАО", 0.78, .030),
    ("Бабушкинский", "СВАО", 0.80, .022), ("Измайлово", "ВАО", 0.82, .030),
    ("Соколиная Гора", "ВАО", 0.80, .022), ("Перово", "ВАО", 0.78, .026),
    ("Марьино", "ЮВАО", 0.75, .034), ("Люблино", "ЮВАО", 0.72, .026),
    ("Кузьминки", "ЮВАО", 0.74, .026), ("Текстильщики", "ЮВАО", 0.70, .018),
    ("Ясенево", "ЮЗАО", 0.80, .028), ("Тёплый Стан", "ЮЗАО", 0.76, .022),
    ("Митино", "СЗАО", 0.80, .030), ("Строгино", "СЗАО", 0.84, .024),
    ("Щукино", "СЗАО", 0.90, .020), ("Хорошёво-Мнёвники", "СЗАО", 0.86, .024),
    ("Северное Тушино", "СЗАО", 0.76, .022), ("Бирюлёво Западное", "ЮАО", 0.68, .022),
    ("Царицыно", "ЮАО", 0.74, .024), ("Чертаново Южное", "ЮАО", 0.70, .026),
    ("Ховрино", "САО", 0.72, .016),
]
_tot = sum(d[3] for d in DISTRICTS)
DISTRICTS = [(a, b, c, w / _tot) for a, b, c, w in DISTRICTS]

# категория: базовый чек, разброс, базовые места, доля
CATEGORIES = [
    ("кафе",        900, .38, 42, .270),
    ("ресторан",   2600, .45, 78, .155),
    ("фастфуд",     450, .30, 26, .180),
    ("кофейня",     520, .32, 22, .155),
    ("пиццерия",    980, .30, 34, .060),
    ("бар",        1400, .40, 40, .075),
    ("столовая",    380, .22, 90, .045),
    ("булочная",    340, .28, 12, .060),
]
CHAINS = ["Шоколадница","Кофе Хауз","Додо Пицца","Теремок","Крошка Картошка",
          "Прайм","One Price Coffee","Вилка-Ложка","Стардог!s","Кулинарная лавка"]

W1 = ["Старый","Уютный","Тёплый","Домашний","Городской","Северный","Первый","Синий",
      "Медный","Хлебный","Вечерний","Липовый","Зелёный","Круглый","Дымный","Ореховый",
      "Летний","Тихий","Красный","Белый"]
W2 = ["дворик","очаг","уголок","стол","квартал","дом","сад","базар","балкон","подвал",
      "терраса","навес","чайник","поднос","колодец","мост","переулок","фонарь","причал","склон"]

def pick(pairs):
    r = rnd.random(); acc = 0.0
    for v, w in pairs:
        acc += w
        if r <= acc: return v
    return pairs[-1][0]

rows = []
seen = set()
for oid in range(1, 10_501):
    dist, okrug, mult, _ = pick([(d, d[3]) for d in DISTRICTS])
    cat = pick([(c, c[4]) for c in CATEGORIES])
    cat_name, base_bill, spread, base_seats, _ = cat

    is_chain = rnd.random() < (0.42 if cat_name in ("фастфуд", "кофейня", "пиццерия") else 0.16)
    if is_chain:
        name = rnd.choice(CHAINS)
    else:
        for _ in range(60):
            name = f"{rnd.choice(W1)} {rnd.choice(W2)}"
            if name not in seen:
                break
        else:
            name = f"{name} {oid}"
        seen.add(name)

    bill = round(base_bill * mult * rnd.lognormvariate(0, spread), -1)
    seats = int(max(4, rnd.gauss(base_seats, base_seats * 0.42)))
    # рейтинг слегка растёт с чеком и падает у сетей
    rating = rnd.gauss(4.1 + 0.00008 * bill - (0.12 if is_chain else 0), 0.45)
    rating = round(min(5.0, max(1.0, rating)), 1)
    reviews = int(max(0, rnd.lognormvariate(3.6, 1.15) * (2.2 if is_chain else 1.0)))
    hours = rnd.choice([
        "круглосуточно", "08:00-22:00", "09:00-23:00", "10:00-22:00",
        "11:00-23:00", "07:00-21:00", "12:00-00:00", "10:00-02:00",
    ])
    lat = round(55.75 + rnd.gauss(0, 0.09), 6)
    lon = round(37.62 + rnd.gauss(0, 0.13), 6)

    rows.append([oid, name, cat_name, 1 if is_chain else 0, dist, okrug,
                 seats, bill, rating, reviews, hours, lat, lon])

# ---- грязь ---------------------------------------------------------------
MISS = ["", "", "н/д", "нет данных"]
def blank(): return rnd.choice(MISS)

# пропуски: места, чек, рейтинг
for r in rnd.sample(rows, int(len(rows) * 0.14)): r[6] = blank()
for r in rnd.sample(rows, int(len(rows) * 0.09)): r[7] = blank()
for r in rnd.sample(rows, int(len(rows) * 0.06)): r[8] = blank()
for r in rnd.sample(rows, int(len(rows) * 0.11)): r[10] = blank()
# абсурдные значения
for r in rnd.sample(rows, 45): r[6] = rnd.choice([0, 1, 1200, 2500])
for r in rnd.sample(rows, 38): r[7] = rnd.choice([0, 10, 95000, 180000])
for r in rnd.sample(rows, 22): r[8] = rnd.choice([0, 5.7, 9.9])
# район записан двумя способами
for r in rows:
    if r[4] == "Тёплый Стан" and rnd.random() < 0.4: r[4] = "Теплый Стан"
    if r[4] == "Хорошёво-Мнёвники" and rnd.random() < 0.35: r[4] = "Хорошево-Мневники"
# категория в разном регистре
for r in rnd.sample(rows, int(len(rows) * 0.07)): r[2] = r[2].upper()
# задвоенные заведения
next_id = len(rows) + 1
extra = []
for r in rnd.sample(rows, 160):
    d = list(r); d[0] = next_id; next_id += 1
    extra.append(d)
rows += extra
rows.sort(key=lambda r: r[0])

path = os.path.join(HERE, "zavedeniya.csv")
with open(path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["object_id","name","category","is_chain","district","okrug",
                "seats","avg_bill","rating","reviews_count","hours","lat","lon"])
    w.writerows(rows)
print(f"zavedeniya.csv: {len(rows):,} строк, {os.path.getsize(path)/1024:.0f} КБ")
