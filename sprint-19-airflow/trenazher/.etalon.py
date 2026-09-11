"""Эталонные решения тренажёра спринта 19. Не подглядывать до решения."""

import re
from collections import defaultdict, deque

import pandas as pd

PRESETS = {
    "@once": None,
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
    "@yearly": "0 0 1 1 *",
}

IDEMPOTENT_OPS = {
    "overwrite_partition": True,
    "truncate_insert": True,
    "upsert": True,
    "create_or_replace": True,
    "append": False,
    "insert": False,
    "increment_counter": False,
    "send_email": False,
    "call_external_api": False,
}


# --- расписание и даты -----------------------------------------------------

def parse_schedule(schedule):
    """Разбор расписания DAG: пресет или cron."""
    if schedule is None:
        return {"schedule": None, "cron": None, "recurring": False,
                "description": "запускается только вручную"}
    s = str(schedule).strip()
    if s in PRESETS:
        cron = PRESETS[s]
        return {"schedule": s, "cron": cron, "recurring": cron is not None,
                "description": ("один раз" if cron is None
                                else f"пресет {s}, эквивалент cron {cron}")}
    parts = s.split()
    if len(parts) != 5:
        raise ValueError(f"cron должен состоять из пяти полей, получено {len(parts)}")
    return {"schedule": s, "cron": s, "recurring": True,
            "description": "cron-выражение"}


def logical_vs_actual(logical_date, schedule_seconds):
    """Логическая дата запуска против фактического момента старта.

    Airflow запускает интервал ПОСЛЕ его окончания: запуск с logical_date
    первого июня стартует второго.
    """
    start = pd.Timestamp(logical_date)
    end = start + pd.Timedelta(seconds=schedule_seconds)
    return {"logical_date": start,
            "data_interval_start": start,
            "data_interval_end": end,
            "runs_at": end,
            "lag_seconds": float(schedule_seconds),
            "note": "интервал обрабатывается после того, как закончился: "
                    "запуск за первое июня стартует второго"}


def catchup_runs(start_date, now, schedule_seconds, catchup=True, max_runs=None):
    """Сколько запусков породит DAG при включении.

    С catchup Airflow досоздаёт все пропущенные интервалы от start_date.
    Без него — только последний.
    """
    start = pd.Timestamp(start_date)
    now = pd.Timestamp(now)
    step = pd.Timedelta(seconds=schedule_seconds)
    if now <= start:
        return {"runs": 0, "dates": [], "catchup": catchup, "capped": False}
    total = int((now - start) // step)
    dates = [start + i * step for i in range(total)]
    if not catchup:
        dates = dates[-1:] if dates else []
    capped = False
    if max_runs is not None and len(dates) > max_runs:
        dates = dates[:max_runs]
        capped = True
    return {"runs": len(dates), "dates": dates, "catchup": catchup,
            "capped": capped,
            "warning": (f"{total} запусков сразу после включения — "
                        "проверь catchup и start_date")
            if catchup and total > 50 else ""}


def backfill_plan_dag(date_from, date_to, schedule_seconds, parallelism=1):
    """План перезапуска за прошлый период."""
    start, end = pd.Timestamp(date_from), pd.Timestamp(date_to)
    if start > end:
        raise ValueError("date_from позже date_to")
    step = pd.Timedelta(seconds=schedule_seconds)
    dates, cur = [], start
    while cur <= end:
        dates.append(cur)
        cur += step
    waves = [dates[i:i + parallelism] for i in range(0, len(dates), parallelism)]
    return {"logical_dates": dates, "runs": len(dates),
            "waves": len(waves), "parallelism": int(parallelism)}


# --- граф ------------------------------------------------------------------

def validate_dag(tasks, deps):
    """Проверка графа: цикл, ссылки на несуществующие задачи, изолированные.

    tasks — список имён, deps — [(из, в)].
    """
    known, problems = set(tasks), []
    for a, b in deps:
        if a not in known:
            problems.append(f"зависимость ссылается на неизвестную задачу: {a}")
        if b not in known:
            problems.append(f"зависимость ссылается на неизвестную задачу: {b}")
    connected = {t for pair in deps for t in pair if t in known}
    isolated = sorted(known - connected)

    indeg = {t: 0 for t in tasks}
    nxt = defaultdict(list)
    for a, b in deps:
        if a in known and b in known:
            nxt[a].append(b)
            indeg[b] += 1
    q = deque(sorted(t for t in tasks if indeg[t] == 0))
    seen = 0
    while q:
        t = q.popleft()
        seen += 1
        for c in sorted(nxt[t]):
            indeg[c] -= 1
            if indeg[c] == 0:
                q.append(c)
    has_cycle = seen != len(tasks)
    if has_cycle:
        problems.append("в графе есть цикл")
    return {"tasks": len(tasks), "edges": len(deps), "isolated": isolated,
            "has_cycle": has_cycle, "problems": problems,
            "valid": not has_cycle and not problems}


def dag_levels(tasks, deps):
    """Топологические уровни: что можно выполнять параллельно."""
    v = validate_dag(tasks, deps)
    if v["has_cycle"]:
        raise ValueError("цикл в графе: уровни не определены")
    parents = defaultdict(list)
    for a, b in deps:
        parents[b].append(a)
    level, changed = {t: 0 for t in tasks}, True
    while changed:
        changed = False
        for t in tasks:
            if parents[t]:
                new = max(level[p] for p in parents[t]) + 1
                if new != level[t]:
                    level[t] = new
                    changed = True
    by_level = defaultdict(list)
    for t in tasks:
        by_level[level[t]].append(t)
    return {"levels": {k: sorted(v) for k, v in sorted(by_level.items())},
            "depth": max(level.values()) + 1 if level else 0,
            "max_parallel": max((len(v) for v in by_level.values()), default=0)}


def critical_path(tasks, deps, durations):
    """Самый длинный путь по времени: он и определяет длительность DAG."""
    lv = dag_levels(tasks, deps)
    parents = defaultdict(list)
    for a, b in deps:
        parents[b].append(a)
    order = [t for _, group in sorted(lv["levels"].items()) for t in group]
    best = {}
    for t in order:
        d = float(durations.get(t, 0))
        if parents[t]:
            p = max(parents[t], key=lambda x: best[x][0])
            best[t] = (best[p][0] + d, best[p][1] + [t])
        else:
            best[t] = (d, [t])
    end = max(best, key=lambda t: best[t][0])
    total_work = sum(float(durations.get(t, 0)) for t in tasks)
    return {"path": best[end][1], "duration": best[end][0],
            "total_task_time": total_work,
            "speedup_if_parallel": total_work / best[end][0] if best[end][0] else None}


def find_hidden_deps(io_map, deps):
    """Задачи, читающие то, что пишет другая, но без объявленной зависимости.

    io_map — {задача: {'reads': [...], 'writes': [...]}}.
    """
    declared = {(a, b) for a, b in deps}
    writers = defaultdict(list)
    for task, io in io_map.items():
        for r in io.get("writes", []):
            writers[r].append(task)
    hidden = []
    for task, io in io_map.items():
        for r in io.get("reads", []):
            for w in writers.get(r, []):
                if w != task and (w, task) not in declared:
                    hidden.append({"reader": task, "writer": w, "resource": r})
    hidden.sort(key=lambda x: (x["reader"], x["writer"], x["resource"]))
    return {"hidden": hidden, "n": len(hidden), "ok": len(hidden) == 0}


# --- надёжность ------------------------------------------------------------

def retry_delays(retries, base_seconds=60, exponential=True, max_seconds=3600):
    """Задержки между попытками."""
    out = []
    for i in range(int(retries)):
        d = base_seconds * (2 ** i) if exponential else base_seconds
        out.append(min(d, max_seconds))
    return {"retries": int(retries), "delays": out,
            "total_seconds": sum(out),
            "exponential": bool(exponential),
            "capped": any(d == max_seconds for d in out)}


def sensor_config(wait_for, expected_wait_s, poke_interval=60, timeout=None):
    """Настройка сенсора: режим ожидания и таймаут."""
    mode = "reschedule" if expected_wait_s > 5 * 60 else "poke"
    if timeout is None:
        timeout = max(int(expected_wait_s * 3), 15 * 60)
    return {"wait_for": wait_for, "mode": mode,
            "poke_interval": int(poke_interval), "timeout": int(timeout),
            "reason": ("ждём долго — освобождаем слот между проверками"
                       if mode == "reschedule"
                       else "ждём недолго — держим слот, это дешевле"),
            "warning": "сенсор без таймаута занимает слот навсегда и "
                       "останавливает весь пайплайн"}


def sla_check(runs, sla_seconds):
    """Нарушения SLA по истории запусков."""
    rows = list(runs)
    if not rows:
        return {"runs": 0, "violations": 0, "share": None, "worst": None}
    bad = [r for r in rows if float(r["duration"]) > sla_seconds]
    worst = max(rows, key=lambda r: float(r["duration"]))
    return {"runs": len(rows), "violations": len(bad),
            "share": len(bad) / len(rows),
            "worst": worst["logical_date"],
            "worst_duration": float(worst["duration"]),
            "sla_seconds": float(sla_seconds),
            "breached_dates": [r["logical_date"] for r in bad]}


def task_idempotency(operation):
    """Безопасна ли операция к повторному запуску."""
    if operation not in IDEMPOTENT_OPS:
        raise ValueError(f"неизвестная операция: {operation}")
    ok = IDEMPOTENT_OPS[operation]
    fixes = {
        "append": "перезаписывай партицию целиком вместо дописывания",
        "insert": "используй upsert по ключу",
        "increment_counter": "считай значение заново, а не прибавляй",
        "send_email": "отправляй из отдельной задачи в конце, с защитой от повтора",
        "call_external_api": "передавай ключ идемпотентности в запросе",
    }
    return {"operation": operation, "idempotent": ok,
            "fix": "" if ok else fixes.get(operation, "нужна защита от повтора")}


# --- секреты и шаблоны -----------------------------------------------------

SECRET_PATTERNS = [
    ("password", r"password\s*=\s*['\"][^'\"]{3,}['\"]"),
    ("aws_key", r"AKIA[0-9A-Z]{16}"),
    ("token", r"(?:token|api_key|apikey|secret)\s*=\s*['\"][^'\"]{8,}['\"]"),
    ("conn_uri", r"\w+://[^:\s'\"]+:[^@\s'\"]+@"),
    ("private_key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def secret_scan(code):
    """Поиск секретов в тексте DAG."""
    found = []
    lines = code.splitlines()
    for rule, pattern in SECRET_PATTERNS:
        rx = re.compile(pattern, re.IGNORECASE)
        for i, line in enumerate(lines, start=1):
            if rx.search(line):
                found.append({"rule": rule, "line": i, "text": line.strip()})
    return {"findings": found, "n": len(found), "clean": len(found) == 0,
            "advice": "" if not found else
                      "секреты живут в Connections и Variables, а не в коде DAG: "
                      "код попадает в git, в логи и в скриншоты"}


def connection_uri(conn_type, host, port, login=None, password=None,
                   schema=None, extra=None):
    """Сборка Airflow connection URI."""
    from urllib.parse import quote, urlencode
    auth = ""
    if login:
        auth = quote(str(login), safe="")
        if password:
            auth += ":" + quote(str(password), safe="")
        auth += "@"
    uri = f"{conn_type}://{auth}{host}:{int(port)}"
    if schema:
        uri += "/" + quote(str(schema), safe="")
    if extra:
        uri += "?" + urlencode(extra)
    masked = uri.replace(quote(str(password), safe=""), "***") if password else uri
    return {"uri": uri, "masked": masked, "conn_type": conn_type}


TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z_][\w.]*)\s*\}\}")


def render_template(text, context):
    """Подстановка макросов Airflow. Неизвестный макрос — KeyError."""
    missing = []

    def sub(m):
        key = m.group(1)
        if key not in context:
            missing.append(key)
            return m.group(0)
        return str(context[key])

    out = TEMPLATE_RE.sub(sub, text)
    if missing:
        raise KeyError(f"нет значений для макросов: {sorted(set(missing))}")
    return out


# --- эксплуатация ----------------------------------------------------------

def failure_summary(runs):
    """Что падает чаще всего по истории запусков."""
    by_task = defaultdict(lambda: {"runs": 0, "failed": 0})
    for r in runs:
        rec = by_task[r["task"]]
        rec["runs"] += 1
        if r["state"] == "failed":
            rec["failed"] += 1
    rows = []
    for task, rec in by_task.items():
        rows.append({"task": task, "runs": rec["runs"], "failed": rec["failed"],
                     "failure_rate": rec["failed"] / rec["runs"] if rec["runs"] else 0.0})
    rows.sort(key=lambda r: (-r["failure_rate"], -r["failed"], r["task"]))
    total = len(runs)
    failed = sum(1 for r in runs if r["state"] == "failed")
    return {"tasks": rows, "total_runs": total, "total_failed": failed,
            "worst": rows[0]["task"] if rows else None}


def pool_plan(concurrent_tasks, slots, task_seconds=60):
    """Хватает ли слотов в пуле."""
    slots = int(slots)
    if slots <= 0:
        raise ValueError("слотов должно быть больше нуля")
    waves = -(-int(concurrent_tasks) // slots)
    return {"tasks": int(concurrent_tasks), "slots": slots, "waves": waves,
            "wall_clock_seconds": waves * float(task_seconds),
            "queued": max(0, int(concurrent_tasks) - slots),
            "enough": int(concurrent_tasks) <= slots}


def dag_review(config):
    """Чек-лист типичных проблем в конфигурации DAG."""
    problems = []
    if config.get("catchup") is True and config.get("start_date"):
        problems.append("catchup включён: проверь, сколько запусков создастся "
                        "от start_date")
    if not config.get("retries"):
        problems.append("нет retries: разовый сетевой сбой уронит запуск")
    if config.get("schedule") and not config.get("start_date"):
        problems.append("есть расписание, но нет start_date")
    if config.get("depends_on_past") and config.get("catchup"):
        problems.append("depends_on_past вместе с catchup: один сбой в прошлом "
                        "останавливает всю цепочку")
    if not config.get("on_failure_callback") and not config.get("email_on_failure"):
        problems.append("нет уведомления об ошибке: о падении узнают от продакта")
    if config.get("max_active_runs", 1) > 1 and not config.get("idempotent"):
        problems.append("несколько одновременных запусков неидемпотентного DAG")
    if config.get("sensor") and not config.get("sensor_timeout"):
        problems.append("сенсор без таймаута занимает слот навсегда")
    return {"problems": problems, "n": len(problems), "ok": len(problems) == 0}
