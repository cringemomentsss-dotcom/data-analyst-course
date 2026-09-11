#!/usr/bin/env python3
"""
Датасет проекта спринта 3: федеральный оператор связи «Мегасеть».

Схема telecom. Данные синтетические, детерминированные.
Запуск: python3 generate_telecom.py  →  CSV в ./out
"""
import csv, os, random
from datetime import datetime, timedelta

rnd = random.Random(777)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
TS = "%Y-%m-%d %H:%M:%S"
START = datetime(2026, 1, 1)
END = datetime(2026, 6, 30, 23, 59, 59)
DAYS = (END.date() - START.date()).days + 1

CITIES = [
    (1, "Алматы", "Алматинская", 2_100_000, 5),
    (2, "Астана", "Акмолинская", 1_400_000, 5),
    (3, "Шымкент", "Туркестанская", 1_100_000, 5),
    (4, "Караганда", "Карагандинская", 500_000, 5),
    (5, "Актобе", "Актюбинская", 530_000, 5),
    (6, "Тараз", "Жамбылская", 360_000, 5),
    (7, "Павлодар", "Павлодарская", 340_000, 5),
    (8, "Усть-Каменогорск", "Абайская", 330_000, 5),
    (9, "Семей", "Абайская", 350_000, 5),
    (10, "Атырау", "Атырауская", 290_000, 5),
    (11, "Костанай", "Костанайская", 250_000, 5),
    (12, "Кызылорда", "Кызылординская", 260_000, 5),
]
CITY_W = [(c[0], w) for c, w in zip(CITIES, [.19,.15,.11,.08,.08,.06,.06,.05,.05,.06,.05,.06])]

# базовый тариф + пакет, сверх пакета — поминутно и погигабайтно
TARIFFS = [
    # id, название, абонплата, минуты, sms, гб, цена мин, цена sms, цена гб
    (1, "Старт",   1490,  300,  50,  10, 3.5, 2.0, 45),
    (2, "Оптимум", 2490,  700, 200,  30, 2.8, 1.5, 35),
    (3, "Макс",    3990, 2000, 500, 100, 2.0, 1.0, 25),
]
TARIFF_W = [(1, .46), (2, .37), (3, .17)]


def pick(pairs):
    r = rnd.random(); acc = 0.0
    for v, w in pairs:
        acc += w
        if r <= acc: return v
    return pairs[-1][0]


def ts(d): return d.strftime(TS)


# ---- клиенты -------------------------------------------------------------
clients = []
N = 2400
for cid in range(1001, 1001 + N):
    # часть абонентов пришла до начала периода
    if rnd.random() < 0.62:
        reg = START - timedelta(days=rnd.randrange(30, 900))
    else:
        reg = START + timedelta(days=rnd.randrange(0, DAYS - 20))
    tariff = pick(TARIFF_W)
    city = pick(CITY_W)
    # отток
    churn = None
    if rnd.random() < 0.135:
        lo = max(reg, START) + timedelta(days=rnd.randrange(20, 160))
        if lo <= END:
            churn = lo
    clients.append([cid, reg.date().isoformat(), city if rnd.random() > 0.026 else None,
                    tariff, churn.date().isoformat() if churn else None,
                    pick([("физлицо", .87), ("юрлицо", .13)])])

by_client = {c[0]: c for c in clients}


def active_days(c):
    lo = max(START, datetime.fromisoformat(c[1]))
    hi = datetime.fromisoformat(c[4]) if c[4] else END
    return lo, min(hi, END)


# интенсивность у каждого абонента своя и коррелирует с тарифом
intensity = {}
for c in clients:
    base = {1: 0.55, 2: 1.0, 3: 1.9}[c[3]]
    intensity[c[0]] = max(0.08, rnd.lognormvariate(0, 0.62) * base)

# ---- звонки, сообщения, интернет ----------------------------------------
calls, msgs, nets = [], [], []
call_id = msg_id = net_id = 0
for c in clients:
    lo, hi = active_days(c)
    days = (hi.date() - lo.date()).days + 1
    if days <= 0:
        continue
    k = intensity[c[0]]

    n_calls = int(rnd.gauss(6.2 * k, 2.4 * k) * days / 7)
    for _ in range(max(0, n_calls)):
        d = lo + timedelta(days=rnd.randrange(days),
                           hours=rnd.choices(range(24), weights=[1,1,1,1,1,2,4,7,9,10,10,9,9,10,10,10,11,12,11,9,7,5,3,2])[0],
                           minutes=rnd.randrange(60))
        dur = round(max(0.1, rnd.lognormvariate(0.85, 0.85)), 1)
        call_id += 1
        calls.append([call_id, c[0], ts(d), dur])

    n_msg = int(rnd.gauss(3.1 * k, 1.8 * k) * days / 7)
    for _ in range(max(0, n_msg)):
        d = lo + timedelta(days=rnd.randrange(days), hours=rnd.randrange(24), minutes=rnd.randrange(60))
        msg_id += 1
        msgs.append([msg_id, c[0], ts(d)])

    n_net = int(rnd.gauss(11 * k, 4 * k) * days / 7)
    for _ in range(max(0, n_net)):
        d = lo + timedelta(days=rnd.randrange(days), hours=rnd.randrange(24), minutes=rnd.randrange(60))
        mb = round(max(0.5, rnd.lognormvariate(4.6, 1.15)), 1)
        net_id += 1
        nets.append([net_id, c[0], ts(d), mb])

# ---- обращения в поддержку ----------------------------------------------
tickets = []
for i in range(1, 900):
    c = rnd.choice(clients)
    lo, hi = active_days(c)
    if (hi - lo).days <= 0:
        continue
    created = lo + timedelta(days=rnd.randrange((hi.date() - lo.date()).days + 1),
                             hours=rnd.randrange(9, 21), minutes=rnd.randrange(60))
    tickets.append([i, c[0], ts(created),
                    pick([("связь", .31), ("счёт", .27), ("тариф", .18),
                          ("интернет", .16), ("прочее", .08)]),
                    pick([("решено", .81), ("отклонено", .11), ("в работе", .08)])])

# ---- грязь ---------------------------------------------------------------
# задвоенные звонки: биллинг записал дважды
for row in rnd.sample(calls, int(len(calls) * 0.006)):
    call_id += 1
    calls.append([call_id] + row[1:])
# звонки нулевой длительности — недозвон, а не разговор
for i in rnd.sample(range(len(calls)), int(len(calls) * 0.021)):
    calls[i][3] = 0.0
# несколько звонков после даты расторжения
churned = [c for c in clients if c[4]]
for c in rnd.sample(churned, min(24, len(churned))):
    d = datetime.fromisoformat(c[4]) + timedelta(days=rnd.randrange(2, 30), hours=rnd.randrange(9, 22))
    if d <= END:
        call_id += 1
        calls.append([call_id, c[0], ts(d), round(rnd.uniform(0.4, 9.0), 1)])

calls.sort(key=lambda r: r[2]); msgs.sort(key=lambda r: r[2]); nets.sort(key=lambda r: r[2])


def dump(name, header, rows):
    with open(os.path.join(OUT, name + ".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    print(f"  {name:14s} {len(rows):>9,}")


print("Генерация «Мегасети»:")
dump("cities", ["city_id", "city", "region", "population", "utc_offset"], CITIES)
dump("tariffs", ["tariff_id", "tariff_name", "monthly_fee", "incl_minutes", "incl_sms",
                 "incl_gb", "price_per_minute", "price_per_sms", "price_per_gb"], TARIFFS)
dump("clients", ["client_id", "reg_date", "city_id", "tariff_id", "churn_date", "client_type"], clients)
dump("calls", ["call_id", "client_id", "call_ts", "duration_min"], calls)
dump("messages", ["message_id", "client_id", "message_ts"], msgs)
dump("internet", ["session_id", "client_id", "session_ts", "mb_used"], nets)
dump("tickets", ["ticket_id", "client_id", "created_ts", "topic", "status"], tickets)
print(f"\nГотово: {OUT}")
