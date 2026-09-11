"""Генерация сырых логов событий для проекта спринта 18.

Пишет gzip-сжатые JSON Lines в out/, разложенные по дням:
    out/events/dt=2026-06-01/part-000.json.gz

Дефекты внесены намеренно — их перечень в README.md рядом.
Случайность зафиксирована: данные воспроизводимы.

Запуск:  python3 sprint-18-pyspark/project/data/generate_logs.py
Обычно вызывается через `make s3`.
"""

import gzip
import json
import os
import random
import shutil
from datetime import datetime, timedelta

SEED = 18
N_EVENTS = 2_000_000
N_USERS = 200_000
N_PRODUCTS = 50_000
START = datetime(2026, 6, 1)
DAYS = 30

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

EVENTS = ["page_view"] * 5 + ["search", "add_to_cart", "checkout_start", "purchase"]
DEVICES_CLEAN = ["ios", "android", "web"]
DEVICE_VARIANTS = {"ios": ["ios", "iOS", "IOS"], "android": ["android", "Android"],
                   "web": ["web", "Web"]}
COUNTRIES = ["GE", "AM", "TR", "DE", "PL", "RS"]
UTM = ["google", "bing", "partner_alpha", "partner_bravo", "instagram",
       "telegram", None]

rnd = random.Random(SEED)


def revenue_value(event):
    """Выручка приходит в трёх разных видах — это дефект, а не фича."""
    if event != "purchase":
        return rnd.choice([None, "", None])
    amount = round(rnd.uniform(5, 500), 2)
    style = rnd.random()
    if style < 0.55:
        return amount              # число
    if style < 0.9:
        return f"{amount:.2f}"     # строка
    return f"{amount:.2f} EUR"     # строка с валютой


def make_event(eid, day):
    """Одно событие. День задаёт партицию, время может из неё выпадать."""
    ts = day + timedelta(seconds=rnd.randrange(86400))
    if rnd.random() < 0.005:                       # опоздавшее событие
        ts -= timedelta(days=rnd.randint(1, 4))
    if rnd.random() < 0.0002:                      # время из будущего
        ts += timedelta(days=rnd.randint(30, 400))

    event = rnd.choice(EVENTS)
    uid = rnd.randrange(1, N_USERS + 1)
    row = {
        "event_id": eid,
        "user_id": f"{uid:08d}" if rnd.random() < 0.15 else uid,
        "ts": ts.strftime("%Y-%m-%dT%H:%M:%S"),
        "event": event,
        "session_id": rnd.randrange(1, 3_000_000),
        "device": rnd.choice(DEVICE_VARIANTS[rnd.choice(DEVICES_CLEAN)]),
        "country": rnd.choice(COUNTRIES) if rnd.random() > 0.02 else None,
        "revenue": revenue_value(event),
        "utm_source": rnd.choice(UTM),
    }
    if event in ("add_to_cart", "purchase"):
        row["product_id"] = rnd.randrange(1, N_PRODUCTS + 1)
    return row


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    per_day = N_EVENTS // DAYS
    eid = 0
    written = {"rows": 0, "dupes": 0, "broken": 0}

    for d in range(DAYS):
        day = START + timedelta(days=d)
        path = os.path.join(OUT, "events", f"dt={day:%Y-%m-%d}")
        os.makedirs(path, exist_ok=True)
        with gzip.open(os.path.join(path, "part-000.json.gz"), "wt",
                       encoding="utf-8") as f:
            for _ in range(per_day):
                eid += 1
                row = make_event(eid, day)
                line = json.dumps(row, ensure_ascii=False)

                if rnd.random() < 0.01:            # битая строка
                    f.write(line[:rnd.randint(10, len(line) - 5)] + "\n")
                    written["broken"] += 1
                    continue

                f.write(line + "\n")
                written["rows"] += 1

                if rnd.random() < 0.02:            # повтор доставки
                    f.write(line + "\n")
                    written["dupes"] += 1
                    written["rows"] += 1

    # справочники: маленькие, годятся для broadcast
    dicts = os.path.join(OUT, "dicts")
    os.makedirs(dicts, exist_ok=True)
    with open(os.path.join(dicts, "users.csv"), "w", encoding="utf-8") as f:
        f.write("user_id,reg_date,country,plan\n")
        for u in range(1, N_USERS + 1):
            reg = datetime(2025, 1, 1) + timedelta(days=rnd.randrange(540))
            f.write(f"{u},{reg:%Y-%m-%d},{rnd.choice(COUNTRIES)},"
                    f"{rnd.choice(['free', 'free', 'free', 'basic', 'pro'])}\n")
    with open(os.path.join(dicts, "products.csv"), "w", encoding="utf-8") as f:
        f.write("product_id,category,price\n")
        cats = ["электроника", "одежда", "дом", "спорт", "книги", "красота"]
        for p in range(1, N_PRODUCTS + 1):
            f.write(f"{p},{rnd.choice(cats)},{round(rnd.uniform(5, 500), 2)}\n")

    size = sum(os.path.getsize(os.path.join(dp, fn))
               for dp, _, fns in os.walk(OUT) for fn in fns)
    print(f"строк записано:    {written['rows']:,}".replace(",", " "))
    print(f"из них дублей:     {written['dupes']:,}".replace(",", " "))
    print(f"битых строк:       {written['broken']:,}".replace(",", " "))
    print(f"партиций:          {DAYS}")
    print(f"объём на диске:    {size / 1024 / 1024:.1f} МБ")


if __name__ == "__main__":
    main()
