#!/usr/bin/env python3
"""
Генератор учебной базы курса «Аналитик данных».

Читает casino.db (курс SQL, август 2026) и достраивает вокруг него
продуктовую витрину: трафик, воронку визитов, эксперименты, платёжные
попытки, бонусы, поддержку, маркетинговые расходы.

Детерминирован: один и тот же сид даёт одни и те же данные.
Результат — CSV-файлы в ./out, загружаются в PostgreSQL через load.sql.

Запуск:  python3 generate.py [путь_к_casino.db]
"""

import csv
import os
import random
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta

SEED = 20260909
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
DEFAULT_DB = os.path.join(HERE, "..", "..", "sql-practice", "casino.db")

TRAFFIC_START = datetime(2026, 1, 1)
TRAFFIC_END = datetime(2026, 6, 30, 23, 59, 59)   # привлечение остановлено 30 июня
TRAFFIC_DAYS = (TRAFFIC_END.date() - TRAFFIC_START.date()).days + 1

rnd = random.Random(SEED)

TS = "%Y-%m-%d %H:%M:%S"


def ts(dt):
    return dt.strftime(TS)


def parse(s):
    return datetime.strptime(s, TS)


# ---------------------------------------------------------------------------
# Каналы привлечения
# ---------------------------------------------------------------------------
#   conv     — доля визитов, доходящих до регистрации
#   p_start  — доля визитов, доходящих до начала регистрации
#   p_done   — вычисляется как conv / p_start

CHANNELS = {
    "affiliate": dict(conv=0.0033, p_start=0.030, utm=[
        ("partner_alpha", "affiliate", ["rev_share", "cpa_de"]),
        ("partner_bravo", "affiliate", ["cpa_br", "cpa_in"]),
        ("partner_charlie", "affiliate", ["hybrid"]),
        ("partner_delta", "affiliate", ["cpa_mx", "rev_share"]),
    ]),
    "ppc": dict(conv=0.0055, p_start=0.040, utm=[
        ("google", "cpc", ["brand", "generic_slots", "competitor"]),
        ("bing", "cpc", ["brand", "generic_slots"]),
    ]),
    "seo": dict(conv=0.0075, p_start=0.050, utm=[
        ("google", "organic", ["(not set)"]),
        ("bing", "organic", ["(not set)"]),
    ]),
    "social": dict(conv=0.0017, p_start=0.020, utm=[
        ("facebook", "paid_social", ["lookalike_de", "interest_slots", "retarget"]),
        ("instagram", "paid_social", ["stories_promo", "reels_promo"]),
        ("tiktok", "paid_social", ["ugc_creators"]),
        ("telegram", "social", ["channel_posts"]),
    ]),
    "direct": dict(conv=0.0130, p_start=0.065, utm=[(None, None, [None])]),
    "email": dict(conv=0.0400, p_start=0.160, utm=[
        ("email", "crm", ["weekly_digest", "winback", "bonus_drop"]),
    ]),
    None: dict(conv=0.0027, p_start=0.030, utm=[(None, None, [None])]),
}

LANDINGS = ["/", "/promo/welcome-bonus", "/games/slots", "/promo/deposit-bonus", "/live-casino"]

# Форма регистрации на мобильном заметно хуже, чем на десктопе.
# Множители нормированы по фактическому распределению устройств, поэтому
# общий уровень воронки не меняется.
DEVICE_START_MULT = {"mobile": 0.8277, "desktop": 1.4119, "tablet": 0.9737}

# ---------------------------------------------------------------------------
# Эксперименты
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    dict(
        experiment_id="exp_001",
        name="onboarding_short_form",
        hypothesis="Сокращение формы регистрации с 6 полей до 3 увеличит долю визитов, "
                   "дошедших до начала регистрации, минимум на 15%.",
        unit="visitor",
        primary_metric="signup_start_rate",
        start_date="2026-03-02", end_date="2026-03-29",
        planned_split="50/50", status="completed",
        effect=0.25,          # относительный лифт p_start в treatment
        bias=None,
    ),
    dict(
        experiment_id="exp_002",
        name="payment_retry_ui",
        hypothesis="Кнопка «Попробовать другой способ» на экране отказа платежа "
                   "увеличит долю успешных депозитов.",
        unit="user",
        primary_metric="deposit_success_rate",
        start_date="2026-03-30", end_date="2026-05-24",
        planned_split="50/50", status="completed",
        effect=0.0,           # эффекта нет, и тест изначально недостаточной мощности
        bias=None,
    ),
    dict(
        experiment_id="exp_003",
        name="bonus_wheel",
        hypothesis="Колесо бонусов на лендинге увеличит долю визитов, дошедших до "
                   "начала регистрации.",
        unit="visitor",
        primary_metric="signup_start_rate",
        start_date="2026-05-04", end_date="2026-05-31",
        planned_split="50/50", status="completed",
        effect=0.0,           # настоящего эффекта нет
        bias="desktop",       # но бакетирование сломано: десктоп чаще попадает в treatment
    ),
]

DECLINE_REASONS = [
    ("insufficient_funds", 0.31), ("do_not_honor", 0.22), ("3ds_failed", 0.17),
    ("expired_card", 0.09), ("limit_exceeded", 0.08), ("fraud_suspect", 0.07),
    ("timeout", 0.06),
]
PROVIDER_BY_METHOD = {
    "card": "checkout", "applepay": "stripe", "ewallet": "skrill",
    "crypto": "coinspaid", "bank_transfer": "paysafe",
}
TICKET_CATEGORIES = ["payment", "bonus", "account", "game", "kyc"]


def weighted(pairs):
    r = rnd.random()
    acc = 0.0
    for value, w in pairs:
        acc += w
        if r <= acc:
            return value
    return pairs[-1][0]


def write_csv(name, header, rows):
    path = os.path.join(OUT, name + ".csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  {name:20s} {len(rows):>8,} строк")
    return len(rows)


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
    db_path = os.path.abspath(db_path)
    if not os.path.exists(db_path):
        sys.exit(f"Не нашёл casino.db по пути {db_path}")
    os.makedirs(OUT, exist_ok=True)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    print(f"Источник: {db_path}")
    print("Перенос ядра:")

    # -- ЧАСТЬ 1: ядро один в один ------------------------------------------
    core = {
        "users": "user_id, reg_ts, reg_date, country, source, device, birth_year, is_verified, vip_level",
        "games": "game_id, game_name, provider, category, rtp",
        "events": "event_id, user_id, event_ts, event_name, platform",
        "sessions": "session_id, user_id, started_at, session_date, duration_sec, device",
        "deposits": "deposit_id, user_id, deposit_ts, amount_eur, method, status, dep_number",
        "withdrawals": "withdrawal_id, user_id, withdrawal_ts, amount_eur, status",
        "bets": "bet_id, user_id, bet_ts, game_id, stake_eur, payout_eur",
    }
    data = {}
    for table, cols in core.items():
        rows = [dict(r) for r in con.execute(f"SELECT {cols} FROM {table} ORDER BY 1")]
        data[table] = rows
        header = [c.strip() for c in cols.split(",")]
        write_csv(table, header, [[r[c] for c in header] for r in rows])

    users = data["users"]
    deposits = data["deposits"]
    by_user = {u["user_id"]: u for u in users}

    # -- ЧАСТЬ 2: посетители -------------------------------------------------
    print("Генерация трафика:")

    users_by_channel = defaultdict(list)
    for u in users:
        users_by_channel[u["source"]].append(u)

    # сезонность: выходные активнее, лёгкий рост к весне
    day_weight = []
    for i in range(TRAFFIC_DAYS):
        d = TRAFFIC_START + timedelta(days=i)
        w = 1.0 + (0.22 if d.weekday() >= 5 else 0.0) + 0.0016 * i
        day_weight.append(w)
    total_w = sum(day_weight)

    def random_ts_weighted():
        r = rnd.random() * total_w
        acc = 0.0
        for i, w in enumerate(day_weight):
            acc += w
            if r <= acc:
                break
        # часовой профиль: пик вечером
        hour = weighted([(h, p) for h, p in zip(
            range(24),
            [.012,.008,.006,.005,.005,.006,.010,.018,.028,.036,.042,.046,
             .048,.049,.050,.052,.058,.068,.080,.092,.095,.083,.060,.043])])
        return TRAFFIC_START + timedelta(days=i, hours=hour,
                                         minutes=rnd.randrange(60), seconds=rnd.randrange(60))

    def pick_utm(channel):
        src, med, camps = rnd.choice(CHANNELS[channel]["utm"])
        camp = rnd.choice(camps)
        # грязь: часть строк facebook приходит с заглавной буквы
        if src == "facebook" and rnd.random() < 0.08:
            src = "Facebook"
        return src, med, camp

    COUNTRIES = [(r["country"], r["n"]) for r in con.execute(
        "SELECT country, COUNT(*) n FROM users GROUP BY 1")]
    ctotal = sum(n for _, n in COUNTRIES)
    COUNTRY_W = [(c, n / ctotal) for c, n in COUNTRIES]
    DEVICE_W = [("mobile", 0.66), ("desktop", 0.28), ("tablet", 0.06)]

    visitors = []
    vid = 10_000_000

    # 2а. визиты, приведшие к регистрации — строятся от существующих игроков
    conv_visitor_of_user = {}
    for u in users:
        vid += 1
        reg = parse(u["reg_ts"])
        first_seen = reg - timedelta(seconds=rnd.randrange(180, 1500))
        src, med, camp = pick_utm(u["source"])
        visitors.append(dict(
            visitor_id=vid, first_seen_ts=first_seen, country=u["country"],
            device=u["device"], utm_source=src, utm_medium=med, utm_campaign=camp,
            landing_page=rnd.choice(LANDINGS), user_id=u["user_id"],
            channel=u["source"], converted=True))
        conv_visitor_of_user[u["user_id"]] = vid

    # 2б. визиты без регистрации — добиваем до целевого объёма по каналам
    for channel, cfg in CHANNELS.items():
        n_users = len(users_by_channel[channel])
        if n_users == 0:
            continue
        target = round(n_users / cfg["conv"])
        for _ in range(target - n_users):
            vid += 1
            src, med, camp = pick_utm(channel)
            visitors.append(dict(
                visitor_id=vid, first_seen_ts=random_ts_weighted(),
                country=weighted(COUNTRY_W), device=weighted(DEVICE_W),
                utm_source=src, utm_medium=med, utm_campaign=camp,
                landing_page=rnd.choice(LANDINGS), user_id=None,
                channel=channel, converted=False))

    visitors.sort(key=lambda v: v["first_seen_ts"])

    # -- ЧАСТЬ 3: эксперименты ----------------------------------------------
    assignments = []
    variant_of = {}          # (exp_id, unit_id) -> variant

    for exp in EXPERIMENTS:
        if exp["unit"] != "visitor":
            continue
        lo = datetime.strptime(exp["start_date"], "%Y-%m-%d")
        hi = datetime.strptime(exp["end_date"], "%Y-%m-%d") + timedelta(days=1)
        for v in visitors:
            if not (lo <= v["first_seen_ts"] < hi):
                continue
            if exp["bias"] == "desktop":
                # сломанный хеш считается от user-agent: десктоп чаще уезжает в treatment
                p_treat = 0.70 if v["device"] == "desktop" else 0.44
            else:
                p_treat = 0.5
            variant = "treatment" if rnd.random() < p_treat else "control"
            variant_of[(exp["experiment_id"], v["visitor_id"])] = variant
            assignments.append([exp["experiment_id"], v["visitor_id"], variant,
                                ts(v["first_seen_ts"])])

    # эксперимент на пользователях: назначаем тем, кто в окне начал депозит
    dep_start_ev = [e for e in data["events"] if e["event_name"] == "deposit_start"]
    for exp in EXPERIMENTS:
        if exp["unit"] != "user":
            continue
        lo = datetime.strptime(exp["start_date"], "%Y-%m-%d")
        hi = datetime.strptime(exp["end_date"], "%Y-%m-%d") + timedelta(days=1)
        seen = set()
        for e in dep_start_ev:
            t = parse(e["event_ts"])
            if not (lo <= t < hi) or e["user_id"] in seen:
                continue
            seen.add(e["user_id"])
            variant = "treatment" if rnd.random() < 0.5 else "control"
            variant_of[(exp["experiment_id"], e["user_id"])] = variant
            assignments.append([exp["experiment_id"], e["user_id"], variant, ts(t)])

    # -- ЧАСТЬ 4: события верхней воронки -----------------------------------
    print("Генерация воронки визитов:")
    page_events = []
    peid = 0

    def emit(visitor, when, name, page):
        nonlocal peid
        peid += 1
        page_events.append([peid, visitor["visitor_id"], ts(when), name, page, visitor["device"]])
        # трекер иногда срабатывает дважды
        if rnd.random() < 0.007:
            peid += 1
            page_events.append([peid, visitor["visitor_id"], ts(when), name, page, visitor["device"]])

    exp_windows = []
    for exp in EXPERIMENTS:
        if exp["unit"] == "visitor":
            exp_windows.append((
                exp["experiment_id"],
                datetime.strptime(exp["start_date"], "%Y-%m-%d"),
                datetime.strptime(exp["end_date"], "%Y-%m-%d") + timedelta(days=1),
                exp["effect"]))

    for v in visitors:
        t0 = v["first_seen_ts"]
        emit(v, t0, "landing_view", v["landing_page"])
        if rnd.random() < 0.22:
            emit(v, t0 + timedelta(seconds=rnd.randrange(20, 400)), "promo_view", "/promo")
        if rnd.random() < 0.09:
            emit(v, t0 + timedelta(seconds=rnd.randrange(60, 900)), "game_demo", "/games/demo")

        if v["converted"]:
            reg = parse(by_user[v["user_id"]]["reg_ts"])
            emit(v, reg - timedelta(seconds=rnd.randrange(30, 300)), "signup_start", "/signup")
            emit(v, reg, "signup_complete", "/signup/done")
            continue

        p = CHANNELS[v["channel"]]["p_start"] * DEVICE_START_MULT[v["device"]]
        for exp_id, lo, hi, effect in exp_windows:
            if lo <= t0 < hi and variant_of.get((exp_id, v["visitor_id"])) == "treatment":
                p *= (1 + effect)
        if rnd.random() < p:
            emit(v, t0 + timedelta(seconds=rnd.randrange(45, 1200)), "signup_start", "/signup")

    # -- ЧАСТЬ 5: платёжные попытки -----------------------------------------
    print("Генерация платежей, бонусов, поддержки:")
    attempts = []
    aid = 0
    for d in sorted(deposits, key=lambda x: x["deposit_ts"]):
        t = parse(d["deposit_ts"])
        method = d["method"]
        provider = PROVIDER_BY_METHOD[method]
        prev_id = None
        if d["status"] == "success" and rnd.random() < 0.28:
            # цепочка неудачных попыток перед успешной: обычно одна, иногда две-три
            n_prev = 1 + (1 if rnd.random() < 0.34 else 0) + (1 if rnd.random() < 0.11 else 0)
            offset = 12 * (n_prev + 1)
            for step in range(n_prev):
                aid += 1
                attempts.append([aid, d["user_id"],
                                 ts(t - timedelta(minutes=offset - 12 * step
                                                  + rnd.randrange(0, 8))),
                                 d["amount_eur"], method, provider, "declined",
                                 weighted(DECLINE_REASONS), prev_id])
                prev_id = aid
        aid += 1
        status = "success" if d["status"] == "success" else "declined"
        reason = None if status == "success" else weighted(DECLINE_REASONS)
        attempts.append([aid, d["user_id"], ts(t), d["amount_eur"], method, provider,
                         status, reason, prev_id])

    # брошенные попытки: форма открыта, оплата не отправлена
    payer_ids = sorted({d["user_id"] for d in deposits})
    for _ in range(380):
        u = by_user[rnd.choice(payer_ids)]
        reg = parse(u["reg_ts"])
        aid += 1
        attempts.append([aid, u["user_id"],
                         ts(reg + timedelta(minutes=rnd.randrange(5, 60 * 24 * 40))),
                         round(rnd.choice([10, 20, 25, 50, 100, 200]) * rnd.uniform(.9, 1.1), 2),
                         rnd.choice(list(PROVIDER_BY_METHOD)), "checkout",
                         "abandoned", None, None])

    # -- ЧАСТЬ 6: бонусы -----------------------------------------------------
    bonuses = []
    bid = 0
    ftd = {}
    for d in deposits:
        if d["status"] == "success" and d["dep_number"] == 1:
            ftd[d["user_id"]] = parse(d["deposit_ts"])
    repeat_payers = sorted({d["user_id"] for d in deposits
                            if d["status"] == "success" and (d["dep_number"] or 0) >= 2})

    def add_bonus(uid, when, btype, amount, wager):
        nonlocal bid
        bid += 1
        st = weighted([("completed", .38), ("expired", .30), ("active", .12), ("cancelled", .20)])
        done = ts(when + timedelta(hours=rnd.randrange(2, 240))) if st == "completed" else None
        bonuses.append([bid, uid, ts(when), btype, amount, wager, st, done])

    for uid, t in ftd.items():
        if rnd.random() < 0.62:
            add_bonus(uid, t + timedelta(seconds=rnd.randrange(5, 120)), "welcome",
                      round(rnd.uniform(10, 150), 2), rnd.choice([20, 25, 30, 35, 40]))
    for uid in repeat_payers:
        if rnd.random() < 0.30:
            add_bonus(uid, ftd.get(uid, parse(by_user[uid]["reg_ts"])) +
                      timedelta(days=rnd.randrange(3, 60)), "reload",
                      round(rnd.uniform(5, 80), 2), rnd.choice([20, 25, 30]))
    for uid in payer_ids:
        if rnd.random() < 0.15:
            add_bonus(uid, ftd.get(uid, parse(by_user[uid]["reg_ts"])) +
                      timedelta(days=rnd.randrange(10, 90)), "cashback",
                      round(rnd.uniform(1, 40), 2), rnd.choice([0, 1, 5]))
    for u in users:
        if rnd.random() < 0.25:
            add_bonus(u["user_id"], parse(u["reg_ts"]) + timedelta(days=rnd.randrange(0, 40)),
                      "freespins", round(rnd.uniform(0, 25), 2), rnd.choice([0, 20, 30]))

    # -- ЧАСТЬ 7: обращения в поддержку --------------------------------------
    failed_by_user = defaultdict(int)
    for d in deposits:
        if d["status"] == "failed":
            failed_by_user[d["user_id"]] += 1

    tickets = []
    tid = 0
    pool = [u["user_id"] for u in users]
    pool += [uid for uid, n in failed_by_user.items() for _ in range(n * 3)]
    for _ in range(520):
        uid = rnd.choice(pool)
        u = by_user[uid]
        created = parse(u["reg_ts"]) + timedelta(minutes=rnd.randrange(10, 60 * 24 * 120))
        if failed_by_user.get(uid):
            cat = weighted([("payment", .55), ("bonus", .15), ("account", .12),
                            ("kyc", .10), ("game", .08)])
        else:
            cat = weighted([("account", .28), ("bonus", .24), ("game", .22),
                            ("kyc", .15), ("payment", .11)])
        tid += 1
        resolved = None
        if rnd.random() > 0.07:
            resolved = created + timedelta(minutes=rnd.randrange(12, 60 * 48))
        csat = None if rnd.random() < 0.35 else weighted(
            [(5, .34), (4, .26), (3, .16), (2, .10), (1, .14)])
        tickets.append([tid, uid, ts(created), ts(resolved) if resolved else None,
                        cat, weighted([("chat", .72), ("email", .28)]), csat])

    # баг выгрузки: у нескольких строк время решения раньше времени создания
    for i in rnd.sample(range(len(tickets)), 4):
        c = parse(tickets[i][2])
        tickets[i][3] = ts(c - timedelta(minutes=rnd.randrange(5, 400)))

    # -- ЧАСТЬ 8: маркетинговые расходы --------------------------------------
    clicks_by_key = defaultdict(int)
    for v in visitors:
        if v["channel"] not in ("ppc", "social", "affiliate"):
            continue
        src = (v["utm_source"] or "").lower()
        clicks_by_key[(v["first_seen_ts"].date(), src, v["utm_campaign"])] += 1

    # Цена клика подобрана так, чтобы CAC за регистрацию был правдоподобным:
    # дешёвый поиск, дорогие партнёры, один партнёр заведомо убыточный.
    CPC = {"google": 0.22, "bing": 0.13, "facebook": 0.085, "instagram": 0.095,
           "tiktok": 0.062, "telegram": 0.048,
           "partner_alpha": 0.34, "partner_bravo": 0.22,
           "partner_charlie": 0.55, "partner_delta": 0.29}
    CTR = {"google": 0.055, "bing": 0.042, "facebook": 0.012, "instagram": 0.014,
           "tiktok": 0.019, "telegram": 0.031,
           "partner_alpha": 0.028, "partner_bravo": 0.024,
           "partner_charlie": 0.033, "partner_delta": 0.021}
    GAPS = {datetime(2026, 2, 14).date(), datetime(2026, 4, 1).date(),
            datetime(2026, 5, 20).date()}

    spend = []
    for (day, src, camp), clicks in sorted(clicks_by_key.items()):
        if day in GAPS or src not in CPC:
            continue
        cpc = CPC[src] * rnd.uniform(0.82, 1.24)
        ctr = CTR[src] * rnd.uniform(0.8, 1.25)
        spend.append([day.isoformat(), src, camp or "(not set)",
                      round(clicks * cpc, 2), int(clicks / ctr), clicks])

    # -- запись -------------------------------------------------------------
    print("Запись CSV:")
    write_csv("visitors", ["visitor_id", "first_seen_ts", "country", "device",
                           "utm_source", "utm_medium", "utm_campaign",
                           "landing_page", "user_id"],
              [[v["visitor_id"], ts(v["first_seen_ts"]), v["country"], v["device"],
                v["utm_source"], v["utm_medium"], v["utm_campaign"],
                v["landing_page"], v["user_id"]] for v in visitors])

    page_events.sort(key=lambda r: (r[2], r[0]))
    write_csv("page_events", ["page_event_id", "visitor_id", "event_ts",
                              "event_name", "page", "device"], page_events)

    write_csv("experiments", ["experiment_id", "name", "hypothesis", "unit",
                              "primary_metric", "start_date", "end_date",
                              "planned_split", "status"],
              [[e["experiment_id"], e["name"], e["hypothesis"], e["unit"],
                e["primary_metric"], e["start_date"], e["end_date"],
                e["planned_split"], e["status"]] for e in EXPERIMENTS])

    write_csv("ab_assignments", ["experiment_id", "unit_id", "variant", "assigned_ts"],
              assignments)

    write_csv("payment_attempts", ["attempt_id", "user_id", "attempt_ts", "amount_eur",
                                   "method", "provider", "status", "decline_reason",
                                   "retry_of"], attempts)

    write_csv("bonuses", ["bonus_id", "user_id", "granted_ts", "bonus_type",
                          "amount_eur", "wager_multiplier", "status", "completed_ts"],
              bonuses)

    write_csv("support_tickets", ["ticket_id", "user_id", "created_ts", "resolved_ts",
                                  "category", "channel", "csat"], tickets)

    write_csv("marketing_spend", ["spend_date", "channel", "campaign", "cost_eur",
                                  "impressions", "clicks"], spend)

    print(f"\nГотово. CSV в {OUT}")


if __name__ == "__main__":
    main()
