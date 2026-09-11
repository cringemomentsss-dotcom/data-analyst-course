#!/usr/bin/env python3
"""
Датасет для проекта спринта 1: выгрузка записей сети барбершопов.

Намеренно грязный — так выглядит настоящая выгрузка из CRM, которую
владелец присылает словами «вот, посмотри что там».

Запуск: python3 generate_barbershop.py
Результат: zapisi-barbershop.csv
"""
import csv, os, random
from datetime import datetime, timedelta

rnd = random.Random(11)
HERE = os.path.dirname(os.path.abspath(__file__))
START = datetime(2026, 1, 1)
DAYS = 181

BRANCHES = ["Центр", "Заречная", "Северный"]
MASTERS = {
    "Центр":     [("Иван Петров", 0.34), ("Артём Соколов", 0.36), ("Лев Гаврилов", 0.30)],
    "Заречная":  [("Марк Дёмин", 0.45), ("Тимур Аскеров", 0.55)],
    "Северный":  [("Олег Рыбак", 0.30), ("Данила Ким", 0.38), ("Роман Швец", 0.32)],
}
SERVICES = [
    ("Стрижка мужская", 1400, 0.40), ("Стрижка + борода", 2100, 0.22),
    ("Оформление бороды", 900, 0.14), ("Стрижка детская", 1000, 0.08),
    ("Бритьё опасной бритвой", 1300, 0.06), ("Камуфляж седины", 1600, 0.05),
    ("Тонирование", 1800, 0.03), ("Стрижка машинкой", 700, 0.02),
]
CHANNELS = [("онлайн", 0.52), ("телефон", 0.31), ("без записи", 0.17)]

# мастера, чьи имена в CRM записаны непоследовательно
ALIASES = {
    "Иван Петров": ["Иван Петров", "Иван П.", "иван петров", " Иван Петров"],
    "Тимур Аскеров": ["Тимур Аскеров", "Тимур А.", "ТИМУР АСКЕРОВ"],
    "Данила Ким": ["Данила Ким", "Д. Ким"],
}


def pick(pairs):
    r = rnd.random(); acc = 0.0
    for v, w in pairs:
        acc += w
        if r <= acc:
            return v
    return pairs[-1][0]


rows = []
rid = 0
clients = list(range(5001, 5001 + 1450))
# у части клиентов есть привычка возвращаться
loyal = rnd.sample(clients, 430)

for d in range(DAYS):
    day = START + timedelta(days=d)
    wd = day.weekday()
    # выходные загруженнее, понедельник самый пустой
    base = {0: 8, 1: 11, 2: 12, 3: 13, 4: 16, 5: 22, 6: 18}[wd]
    base = int(base * rnd.uniform(0.75, 1.3) * (1 + 0.0012 * d))
    for _ in range(base):
        branch = pick([(b, w) for b, w in zip(BRANCHES, [0.42, 0.28, 0.30])])
        master = pick(MASTERS[branch])
        chosen = pick([(x[0], x[2]) for x in SERVICES])
        service, price = next((n, pr) for n, pr, _ in SERVICES if n == chosen)
        hour = rnd.choices(range(10, 21), weights=[4,5,6,7,7,8,9,11,12,10,6])[0]
        minute = rnd.choice([0, 15, 30, 45])
        client = rnd.choice(loyal) if rnd.random() < 0.46 else rnd.choice(clients)
        status = "выполнена"
        if rnd.random() < 0.061:
            status = "отменена" if rnd.random() < 0.62 else "неявка"
        # цена гуляет: скидки, наценка выходного дня
        p = price
        if rnd.random() < 0.11:
            p = round(price * rnd.choice([0.8, 0.85, 0.9]))
        elif wd >= 5 and rnd.random() < 0.25:
            p = round(price * 1.1)
        rid += 1
        # имя мастера пишется как попало
        mname = rnd.choice(ALIASES[master]) if master in ALIASES else master
        # дата в двух форматах
        dstr = day.strftime("%d.%m.%Y") if rnd.random() < 0.83 else day.strftime("%Y-%m-%d")
        # цена то числом, то текстом
        if rnd.random() < 0.09:
            pstr = f"{p} р."
        elif rnd.random() < 0.06:
            pstr = str(p).replace(".", ",") + ",00"
        else:
            pstr = str(p)
        rows.append([rid, dstr, f"{hour:02d}:{minute:02d}", branch, mname,
                     service if rnd.random() > 0.011 else "",
                     pstr, client, pick(CHANNELS), status])

# задвоенные записи: администратор оформил дважды
for i in rnd.sample(range(len(rows)), 47):
    dup = list(rows[i]); rid += 1; dup[0] = rid
    rows.append(dup)

# опечатка в названии филиала
for i in rnd.sample(range(len(rows)), 23):
    if rows[i][3] == "Заречная":
        rows[i][3] = "Заречная "

rows.sort(key=lambda r: int(r[0]))

out = os.path.join(HERE, "zapisi-barbershop.csv")
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id_zapisi", "data", "vremya", "filial", "master", "usluga",
                "cena", "id_klienta", "kanal_zapisi", "status"])
    w.writerows(rows)
print(f"{len(rows)} строк → {out}")
