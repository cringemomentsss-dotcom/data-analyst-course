#!/usr/bin/env python3
"""
Датасет итогового проекта модуля 4: интернет-магазин BitMotion Kit.

Схема shop. Внутри — A/B-тест новой версии сайта.
Запуск: python3 generate_shop.py  →  CSV в ./out
"""
import csv, os, random
from datetime import datetime, timedelta

rnd = random.Random(4040)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
TS = "%Y-%m-%d %H:%M:%S"
START = datetime(2026, 1, 1)
END = datetime(2026, 6, 30, 23, 59, 59)
DAYS = (END.date() - START.date()).days + 1

# Окно эксперимента: 8 недель
EXP_START = datetime(2026, 4, 6)
EXP_END = datetime(2026, 5, 31, 23, 59, 59)

COUNTRIES = [("DE",.21),("PL",.16),("CZ",.11),("NL",.10),("SE",.09),
             ("AT",.08),("FR",.09),("ES",.08),(None,.08)]
DEVICES = [("mobile",.61),("desktop",.31),("tablet",.08)]
CHANNELS = [("organic",.23),("paid_search",.22),("social",.18),
            ("email",.13),("affiliate",.13),("direct",.11)]
CATS = [("наушники",.19),("клавиатуры",.16),("мыши",.15),("мониторы",.10),
        ("зарядки",.14),("чехлы",.13),("колонки",.08),("хабы",.05)]


def pick(pairs):
    r = rnd.random(); acc = 0.0
    for v, w in pairs:
        acc += w
        if r <= acc: return v
    return pairs[-1][0]


def ts(d): return d.strftime(TS)


# --------------------------------------------------------------- покупатели
users = []
for uid in range(1, 60_001):
    su = START + timedelta(days=int(rnd.random() ** 1.2 * DAYS),
                           hours=rnd.randrange(24), minutes=rnd.randrange(60))
    users.append([uid, ts(su), pick(COUNTRIES), pick(DEVICES), pick(CHANNELS)])
signup_of = {u[0]: datetime.strptime(u[1], TS) for u in users}
dev_of = {u[0]: u[3] for u in users}

# ------------------------------------------------------------ эксперимент
# Новая версия сайта. Дизайн: конверсия растёт, но средний чек падает —
# классическая ловушка «подняли конверсию, уронили выручку».
assign = []
variant_of = {}
for u in users:
    su = signup_of[u[0]]
    if not (EXP_START <= su <= EXP_END):
        continue
    v = "treatment" if rnd.random() < 0.5 else "control"
    variant_of[u[0]] = v
    assign.append([u[0], v, ts(su)])

BASE_CR = 0.0620          # конверсия в покупку у контроля
CR_LIFT = 0.185           # относительный лифт в treatment
AOV_BASE = 84.0
AOV_DROP = 0.115          # средний чек в treatment ниже

# ----------------------------------------------------------------- события
FUNNEL = ["view_item", "add_to_cart", "checkout_start", "purchase"]
events, sessions, orders = [], [], []
eid = sid = oid = 0

for u in users:
    uid = u[0]
    su = signup_of[uid]
    v = variant_of.get(uid)
    cr = BASE_CR * (1 + CR_LIFT) if v == "treatment" else BASE_CR
    aov_mult = (1 - AOV_DROP) if v == "treatment" else 1.0

    n_sessions = max(1, int(rnd.gauss(2.6, 1.7)))
    for k in range(n_sessions):
        when = su + timedelta(days=int(rnd.random() ** 1.4 * 40),
                              hours=rnd.randrange(24), minutes=rnd.randrange(60))
        if when > END:
            continue
        dur = int(max(15, rnd.lognormvariate(5.1, 0.85)))
        sid += 1
        sessions.append([sid, uid, ts(when), dur, dev_of[uid]])

        # воронка внутри сессии
        eid += 1
        events.append([eid, uid, ts(when + timedelta(seconds=rnd.randrange(5, 40))),
                       "view_item", pick(CATS)])
        if rnd.random() < 0.31:
            eid += 1
            events.append([eid, uid, ts(when + timedelta(seconds=rnd.randrange(40, 200))),
                           "add_to_cart", pick(CATS)])
            if rnd.random() < 0.46:
                eid += 1
                events.append([eid, uid, ts(when + timedelta(seconds=rnd.randrange(200, 500))),
                               "checkout_start", None])

    # покупка: одна на пользователя максимум (упрощение)
    if rnd.random() < cr:
        when = su + timedelta(days=int(rnd.random() ** 1.5 * 40),
                              hours=rnd.randrange(24), minutes=rnd.randrange(60))
        if when <= END:
            items = pick([(1, .58), (2, .26), (3, .11), (4, .05)])
            rev = round(AOV_BASE * aov_mult * items ** 0.72
                        * rnd.lognormvariate(0, 0.34), 2)
            status = pick([("delivered", .915), ("cancelled", .052), ("returned", .033)])
            oid += 1
            orders.append([oid, uid, ts(when), rev, items, status])
            eid += 1
            events.append([eid, uid, ts(when), "purchase", None])

# ------------------------------------------------------------------- грязь
# задвоенные заказы
next_o = oid + 1
extra = []
for r in rnd.sample(orders, 180):
    d = list(r); d[0] = next_o; next_o += 1
    extra.append(d)
orders += extra
# сессии нулевой длительности
for r in rnd.sample(sessions, 260):
    r[3] = 0
# задвоенные события
next_e = eid + 1
ex_ev = []
for r in rnd.sample(events, int(len(events) * 0.006)):
    d = list(r); d[0] = next_e; next_e += 1
    ex_ev.append(d)
events += ex_ev

events.sort(key=lambda r: r[2])
sessions.sort(key=lambda r: r[2])
orders.sort(key=lambda r: r[2])


def dump(name, header, rows):
    with open(os.path.join(OUT, name + ".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    print(f"  {name:16s} {len(rows):>9,}")


print("Генерация BitMotion Kit:")
dump("users", ["user_id", "signup_ts", "country", "device", "channel"], users)
dump("sessions", ["session_id", "user_id", "started_at", "duration_sec", "device"], sessions)
dump("events", ["event_id", "user_id", "event_ts", "event_name", "category"], events)
dump("orders", ["order_id", "user_id", "created_at", "revenue", "items_count", "status"], orders)
dump("ab_assignments", ["user_id", "variant", "assigned_ts"], assign)
dump("experiment", ["experiment_id", "name", "hypothesis", "unit", "primary_metric",
                    "start_date", "end_date", "planned_split", "status"],
     [["exp_site_v2", "new_site_version",
       "Новая версия сайта повысит конверсию посетителя в покупку минимум на 10%.",
       "user", "purchase_conversion", EXP_START.date().isoformat(),
       EXP_END.date().isoformat(), "50/50", "completed"]])
print(f"\nГотово: {OUT}")
