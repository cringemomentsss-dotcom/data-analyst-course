#!/usr/bin/env python3
"""
Датасет проекта спринта 4: онлайн-игра «Секреты Темнолесья».

Схема game. Данные синтетические, детерминированные.
Запуск: python3 generate_game.py  →  CSV в ./out
"""
import csv, os, random
from datetime import datetime, timedelta

rnd = random.Random(31337)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
TS = "%Y-%m-%d %H:%M:%S"
START = datetime(2025, 9, 1)
END = datetime(2026, 6, 30, 23, 59, 59)
DAYS = (END.date() - START.date()).days + 1

COUNTRIES = [("DE",.14),("US",.13),("BR",.12),("PL",.10),("TR",.09),("RU",.09),
             ("FR",.07),("ES",.07),("IN",.07),("MX",.06),(None,.06)]
PLATFORMS = [("ios",.31),("android",.44),("pc",.25)]
CHANNELS = [("ua_facebook",.27),("ua_google",.21),("ua_tiktok",.14),
            ("organic",.19),("influencer",.11),("cross_promo",.08)]

CATEGORIES = {
    "cosmetic":  (1.99, 24.99, .34),
    "booster":   (0.99,  9.99, .26),
    "currency":  (4.99, 99.99, .22),
    "battlepass":(9.99, 19.99, .09),
    "bundle":    (14.99, 79.99, .09),
}
RARITY = [("common",.44),("rare",.31),("epic",.18),("legendary",.07)]
PROMO = [
    ("WELCOME15", 15, "2025-09-01", "2026-06-30"),
    ("AUTUMN25",  25, "2025-09-15", "2025-11-30"),
    ("WINTER30",  30, "2025-12-15", "2026-01-15"),
    ("RETURN20",  20, "2026-02-01", "2026-06-30"),
    ("SPRING10",  10, "2026-03-01", "2026-05-31"),
]

def pick(pairs):
    r=rnd.random(); acc=0.0
    for v,w in pairs:
        acc+=w
        if r<=acc: return v
    return pairs[-1][0]

def ts(d): return d.strftime(TS)

# ---- предметы ------------------------------------------------------------
PREF = ["Тенистый","Лунный","Костяной","Медный","Багровый","Ледяной","Древний",
        "Ржавый","Изумрудный","Пепельный","Терновый","Золочёный"]
NOUN = ["клинок","плащ","амулет","сундук","венец","фонарь","посох","маска",
        "перчатки","компас","печать","рог"]
items=[]; seen=set()
for iid in range(1, 61):
    cat = pick([(c, CATEGORIES[c][2]) for c in CATEGORIES])
    lo, hi, _ = CATEGORIES[cat]
    while True:
        name = f"{rnd.choice(PREF)} {rnd.choice(NOUN)}"
        if name not in seen: seen.add(name); break
    price = round(rnd.uniform(lo, hi), 2)
    items.append([iid, name, cat, pick(RARITY), price])
item_price = {i[0]: i[4] for i in items}
item_w = [(i[0], 1.0) for i in items]
# популярность предметов — длинный хвост
w = sorted((rnd.paretovariate(1.3) for _ in items), reverse=True)
tot = sum(w); item_w = [(i[0], x/tot) for i, x in zip(items, w)]

# ---- игроки --------------------------------------------------------------
players=[]
N=12000
for pid in range(1, N+1):
    reg = START + timedelta(days=int(rnd.random()**1.25 * DAYS))
    players.append([pid, reg.date().isoformat(), pick(COUNTRIES),
                    pick(PLATFORMS), pick(CHANNELS)])
reg_of = {p[0]: datetime.fromisoformat(p[1]) for p in players}

# срок жизни: большинство отваливается в первую неделю
lifetime = {}
for p in players:
    r = rnd.random()
    if r < 0.44:   d = rnd.randrange(0, 3)
    elif r < 0.72: d = rnd.randrange(3, 21)
    elif r < 0.92: d = rnd.randrange(21, 110)
    else:          d = rnd.randrange(110, 300)
    lifetime[p[0]] = d

# склонность платить
paying = {}
for p in players:
    base = {"ua_facebook":.082,"ua_google":.105,"ua_tiktok":.055,
            "organic":.168,"influencer":.090,"cross_promo":.072}[p[4]]
    paying[p[0]] = rnd.random() < base * (1.6 if lifetime[p[0]] > 21 else 0.55)

# ---- сессии и уровни -----------------------------------------------------
sessions=[]; levels=[]; sid=0
for p in players:
    pid=p[0]; reg=reg_of[pid]; life=lifetime[pid]
    n = max(1, int(rnd.gauss(life*0.75+1.6, life*0.3+1)))
    level=1
    levels.append([pid, 1, ts(reg)])
    days = sorted(rnd.choices(range(life+1), k=n))
    for off in days:
        when = reg + timedelta(days=off, hours=rnd.choices(range(24),
               weights=[3,2,1,1,1,1,2,3,4,5,6,6,6,6,6,7,8,10,11,11,10,8,6,4])[0],
               minutes=rnd.randrange(60))
        if when > END: continue
        dur = round(max(1.0, rnd.lognormvariate(2.65, 0.85)), 1)
        gained = min(3, max(0, int(rnd.gauss(0.75, 0.9))))
        sid+=1
        sessions.append([sid, pid, ts(when), dur, level, level+gained,
                         p[3]])
        for _ in range(gained):
            level += 1
            levels.append([pid, level, ts(when + timedelta(minutes=rnd.uniform(1, dur)))])

# ---- покупки -------------------------------------------------------------
purchases=[]; pu=0
promo_valid = {c: (datetime.fromisoformat(a), datetime.fromisoformat(b))
               for c, _, a, b in PROMO}
promo_disc = {c: d for c, d, _, _ in PROMO}
for p in players:
    pid=p[0]
    if not paying[pid]: continue
    life=lifetime[pid]
    # платящие распределены с тяжёлым хвостом: медиана 2-3 покупки,
    # киты доходят до сотни — как в реальной мобильной игре
    k = min(max(1, int(rnd.paretovariate(0.85))), 200)
    for _ in range(k):
        off = int(rnd.random()**1.7 * (life+1))
        when = reg_of[pid] + timedelta(days=off, hours=rnd.randrange(24), minutes=rnd.randrange(60))
        if when > END: continue
        iid = pick(item_w)
        price = item_price[iid]
        code = None
        if rnd.random() < 0.23:
            code = rnd.choice(list(promo_disc))
            price = round(price * (1 - promo_disc[code]/100), 2)
        pu+=1
        purchases.append([pu, pid, iid, ts(when), price, code, "paid"])

# возвраты
for row in rnd.sample(purchases, int(len(purchases)*0.018)):
    row[6] = "refunded"

# ---- грязь ---------------------------------------------------------------
# промокод применён вне срока действия
off_window = [r for r in purchases if r[5]]
for row in rnd.sample(off_window, max(1, int(len(off_window)*0.04))):
    lo, hi = promo_valid[row[5]]
    t = datetime.strptime(row[3], TS)
    if lo <= t <= hi:
        row[3] = ts(hi + timedelta(days=rnd.randrange(3, 40)))
# задвоенные покупки
for row in rnd.sample(purchases, int(len(purchases)*0.007)):
    pu+=1
    purchases.append([pu]+row[1:])

purchases.sort(key=lambda r: r[3])
sessions.sort(key=lambda r: r[2])
levels.sort(key=lambda r: r[2])

def dump(name, header, rows):
    with open(os.path.join(OUT, name+".csv"), "w", newline="", encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(header); w.writerows(rows)
    print(f"  {name:14s} {len(rows):>9,}")

print("Генерация «Секретов Темнолесья»:")
dump("players", ["player_id","reg_date","country","platform","channel"], players)
dump("items", ["item_id","item_name","category","rarity","base_price"], items)
dump("promo_codes", ["code","discount_pct","valid_from","valid_to"],
     [[c,d,a,b] for c,d,a,b in PROMO])
dump("sessions", ["session_id","player_id","started_at","duration_min",
                  "level_start","level_end","platform"], sessions)
dump("levels", ["player_id","level","reached_at"], levels)
dump("purchases", ["purchase_id","player_id","item_id","purchase_ts",
                   "price_paid","promo_code","status"], purchases)
print(f"\nГотово: {OUT}")
