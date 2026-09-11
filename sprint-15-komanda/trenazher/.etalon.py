"""Эталонные решения тренажёра спринта 15. Не подглядывать до решения."""

import json
import re

import numpy as np
import pandas as pd

SEVERITY_ORDER = ["blocker", "major", "minor", "nit"]


# --- тесты на данные -------------------------------------------------------

def _result(name, passed, failed_rows=0, detail="", severity="error"):
    return {"test": name, "passed": bool(passed), "failed_rows": int(failed_rows),
            "detail": detail, "severity": severity}


def test_unique(df, columns, severity="error"):
    """Ключ уникален."""
    cols = [columns] if isinstance(columns, str) else list(columns)
    dup = df.duplicated(subset=cols, keep=False)
    n = int(dup.sum())
    ex = df.loc[dup, cols].drop_duplicates().head(3).to_dict("records")
    return _result(f"unique({','.join(cols)})", n == 0, n,
                   f"дубли ключа: {ex}" if n else "", severity)


def test_not_null(df, columns, severity="error"):
    """В обязательных полях нет пропусков."""
    cols = [columns] if isinstance(columns, str) else list(columns)
    counts = {c: int(df[c].isna().sum()) for c in cols}
    n = sum(counts.values())
    bad = {c: v for c, v in counts.items() if v}
    return _result(f"not_null({','.join(cols)})", n == 0, n,
                   f"пропуски: {bad}" if bad else "", severity)


def test_accepted_values(df, column, values, severity="error"):
    """Значения столбца входят в разрешённый список. NULL считается нарушением."""
    allowed = set(values)
    bad_mask = ~df[column].isin(allowed)
    n = int(bad_mask.sum())
    found = sorted({str(v) for v in df.loc[bad_mask, column].unique()})[:5]
    return _result(f"accepted_values({column})", n == 0, n,
                   f"недопустимые: {found}" if n else "", severity)


def test_range(df, column, lo=None, hi=None, severity="error"):
    """Числовые значения попадают в диапазон. Границы включаются."""
    x = pd.to_numeric(df[column], errors="coerce")
    bad = pd.Series(False, index=df.index)
    if lo is not None:
        bad = bad | (x < lo)
    if hi is not None:
        bad = bad | (x > hi)
    bad = bad | x.isna()
    n = int(bad.sum())
    return _result(f"range({column}, {lo}..{hi})", n == 0, n,
                   f"вне диапазона или не число: {n}" if n else "", severity)


def test_relationships(child, parent, child_col, parent_col, severity="error"):
    """Каждое непустое значение внешнего ключа есть в родительской таблице."""
    keys = set(parent[parent_col].dropna())
    present = child[child_col].dropna()
    bad_mask = ~present.isin(keys)
    n = int(bad_mask.sum())
    orphans = sorted({str(v) for v in present[bad_mask].unique()})[:5]
    return _result(f"relationships({child_col}->{parent_col})", n == 0, n,
                   f"сироты: {orphans}" if n else "", severity)


def test_recon(mart_total, source_total, tol=0.001, severity="error"):
    """Витрина сходится с источником в пределах относительного допуска."""
    m, s = float(mart_total), float(source_total)
    diff = m - s
    ok = abs(diff) <= tol * max(1.0, abs(s))
    return _result("recon", ok, 0 if ok else 1,
                   f"витрина {m}, источник {s}, расхождение {diff:.4f}"
                   if not ok else "", severity)


def test_freshness(df, ts_col, now, max_lag_hours=24, severity="warn"):
    """Самая свежая строка не старше допустимого отставания."""
    ts = pd.to_datetime(df[ts_col], errors="coerce").dropna()
    if len(ts) == 0:
        return _result(f"freshness({ts_col})", False, 1, "нет валидных дат", severity)
    last = ts.max()
    lag = (pd.Timestamp(now) - last).total_seconds() / 3600
    ok = lag <= max_lag_hours
    r = _result(f"freshness({ts_col})", ok, 0 if ok else 1,
                f"отставание {lag:.1f} ч при допуске {max_lag_hours}" if not ok else "",
                severity)
    r["lag_hours"] = float(lag)
    return r


def run_suite(results):
    """Свод прогона тестов. Витрина публикуется, только если нет error-провалов."""
    rows = list(results)
    failed = [r for r in rows if not r["passed"]]
    errors = [r for r in failed if r.get("severity", "error") == "error"]
    warns = [r for r in failed if r.get("severity", "error") == "warn"]
    return {"total": len(rows), "passed": len(rows) - len(failed),
            "failed": len(failed), "errors": len(errors), "warnings": len(warns),
            "can_publish": len(errors) == 0,
            "failed_tests": [r["test"] for r in failed]}


# --- воспроизводимость -----------------------------------------------------

def resolve_params(defaults, overrides=None, required=None):
    """Параметры расчёта: значения по умолчанию, переопределения, обязательные.

    Переопределение ключа, которого нет в defaults, — ошибка: почти
    всегда это опечатка в имени параметра.
    """
    over = dict(overrides or {})
    unknown = sorted(set(over) - set(defaults))
    if unknown:
        raise KeyError(f"неизвестные параметры: {unknown}")
    params = dict(defaults)
    params.update(over)
    missing = sorted([k for k in (required or []) if params.get(k) is None])
    if missing:
        raise ValueError(f"не заданы обязательные параметры: {missing}")
    return params


def deterministic_sample(df, n, seed, stratify_col=None):
    """Воспроизводимая выборка. Один seed — одна и та же выборка всегда."""
    if n <= 0:
        raise ValueError("n должно быть больше нуля")
    if n >= len(df):
        return df.copy()
    if stratify_col is None:
        return df.sample(n=n, random_state=seed).sort_index()
    parts = []
    groups = list(df.groupby(stratify_col, observed=True))
    total = len(df)
    taken = 0
    for i, (_, g) in enumerate(groups):
        k = n - taken if i == len(groups) - 1 else int(round(n * len(g) / total))
        k = max(0, min(k, len(g), n - taken))
        if k:
            parts.append(g.sample(n=k, random_state=seed))
        taken += k
    out = pd.concat(parts) if parts else df.head(0)
    return out.sort_index()


def notebook_run_order(notebook):
    """Проверка, что ноутбук запускается сверху вниз.

    notebook — словарь формата .ipynb или путь к файлу.
    Порядок нарушен, если номера выполнения кодовых ячеек не образуют
    строго возрастающую последовательность. Ячейки без номера — не
    запускались.
    """
    if isinstance(notebook, (str, bytes)):
        with open(notebook, encoding="utf-8") as f:
            notebook = json.load(f)
    code = [c for c in notebook.get("cells", []) if c.get("cell_type") == "code"]
    counts = [c.get("execution_count") for c in code]
    ran = [(i, c) for i, c in enumerate(counts) if c is not None]
    not_run = [i for i, c in enumerate(counts) if c is None]
    seq = [c for _, c in ran]
    in_order = all(a < b for a, b in zip(seq, seq[1:]))
    return {"code_cells": len(code), "executed": len(ran),
            "not_executed": not_run, "order": seq,
            "in_order": bool(in_order),
            "reproducible": bool(in_order and not not_run)}


# --- ревью -----------------------------------------------------------------

SQL_SMELLS = [
    ("select_star", r"select\s+\*", "SELECT * — витрина ломается при изменении схемы"),
    ("implicit_join", r"\bfrom\s+\w+(?:\s+(?:as\s+)?\w+)?\s*,\s*\w+",
     "неявное соединение через запятую"),
    ("bare_join", r"(?<!inner\s)(?<!left\s)(?<!right\s)(?<!full\s)(?<!cross\s)\bjoin\b",
     "тип соединения не указан явно"),
    ("hardcoded_date", r"'\d{4}-\d{2}-\d{2}'", "дата захардкожена вместо параметра"),
    ("between_timestamp", r"between\s+'\d{4}-\d{2}-\d{2}'\s+and\s+'\d{4}-\d{2}-\d{2}'",
     "BETWEEN по датам на timestamp теряет последний день"),
    ("not_equal_null", r"<>\s*'|!=\s*'", "сравнение <> отбрасывает NULL молча"),
]


def sql_smells(sql):
    """Поиск типичных проблем в тексте SQL.

    Возвращает список находок по порядку правил: {'rule', 'line', 'text',
    'message'}. Комментарии не проверяются.
    """
    lines = sql.splitlines()
    clean = []
    for i, ln in enumerate(lines, start=1):
        body = re.sub(r"--.*$", "", ln)
        clean.append((i, ln.strip(), body.lower()))
    out = []
    for rule, pattern, message in SQL_SMELLS:
        rx = re.compile(pattern, re.IGNORECASE)
        for i, raw, body in clean:
            if rx.search(body):
                out.append({"rule": rule, "line": i, "text": raw, "message": message})
    return out


DIFF_FILE = re.compile(r"^\+\+\+ b/(.+)$")


def diff_stats(diff_text, big_pr_lines=400):
    """Разбор unified diff: файлы, добавлено, удалено, вердикт по размеру."""
    files, added, removed = [], 0, 0
    for line in diff_text.splitlines():
        m = DIFF_FILE.match(line)
        if m:
            files.append(m.group(1))
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    total = added + removed
    return {"files": files, "n_files": len(files), "added": added,
            "removed": removed, "total_changed": total,
            "too_big": bool(total > big_pr_lines),
            "verdict": ("разбить на несколько PR" if total > big_pr_lines
                        else "размер приемлемый")}


def classify_severity(changes_result, breaks_pipeline=False, is_style=False,
                      is_risky=False):
    """Классификация замечания по тяжести.

    blocker — меняет результат или ломает пайплайн;
    major — не меняет результат сейчас, но создаёт риск;
    minor — читаемость, дублирование, неудобство;
    nit — вкусовое, правка необязательна.
    """
    if changes_result or breaks_pipeline:
        return "blocker"
    if is_risky:
        return "major"
    if is_style:
        return "nit"
    return "minor"


def review_finding(location, problem, suggestion, severity):
    """Одно замечание ревью в проверяемом виде.

    Замечание без места, без предложения или с неизвестной тяжестью
    отправлять нельзя: коллега не сможет ничего с ним сделать.
    """
    if severity not in SEVERITY_ORDER:
        raise ValueError(f"тяжесть должна быть одной из {SEVERITY_ORDER}")
    for name, value in (("location", location), ("problem", problem),
                        ("suggestion", suggestion)):
        if not str(value).strip():
            raise ValueError(f"поле {name} не может быть пустым")
    return {"location": str(location).strip(), "problem": str(problem).strip(),
            "suggestion": str(suggestion).strip(), "severity": severity,
            "blocking": severity == "blocker"}


def review_summary(findings):
    """Свод ревью и вердикт по PR."""
    by = {s: 0 for s in SEVERITY_ORDER}
    for f in findings:
        by[f["severity"]] = by.get(f["severity"], 0) + 1
    blockers = by["blocker"]
    if blockers:
        verdict = "вернуть на доработку"
    elif by["major"]:
        verdict = "принять с правками"
    else:
        verdict = "принять"
    return {"total": len(findings), "by_severity": by, "blockers": blockers,
            "verdict": verdict, "can_merge": blockers == 0,
            "mandatory": [f for f in findings if f["severity"] in ("blocker", "major")],
            "optional": [f for f in findings if f["severity"] in ("minor", "nit")]}


# --- требования ------------------------------------------------------------

REQUIRED_TASK_FIELDS = ["question", "metric_definition", "period", "segments",
                        "decision", "deadline"]

FIELD_QUESTIONS = {
    "question": "на какой вопрос отвечаем",
    "metric_definition": "что именно считается и по какому определению",
    "period": "за какой период",
    "segments": "в каких разрезах",
    "decision": "какое решение будет принято по результату",
    "deadline": "к какому сроку",
}


def requirements_gaps(task, required=None):
    """Чего не хватает в постановке задачи.

    Возвращает {'missing', 'questions', 'ready'}. Пустая строка и None —
    это отсутствие, а не значение.
    """
    fields = list(required or REQUIRED_TASK_FIELDS)
    missing = [f for f in fields
               if task.get(f) is None or not str(task.get(f)).strip()]
    return {"missing": missing,
            "questions": [FIELD_QUESTIONS.get(f, f) for f in missing],
            "ready": len(missing) == 0}


REQUIRED_SPEC_FIELDS = ["name", "definition", "numerator", "denominator",
                        "unit", "period", "owner", "sql_ref"]


def metric_spec_complete(spec, required=None):
    """Полнота спецификации метрики для дата-словаря."""
    fields = list(required or REQUIRED_SPEC_FIELDS)
    missing = [f for f in fields
               if spec.get(f) is None or not str(spec.get(f)).strip()]
    filled = len(fields) - len(missing)
    return {"missing": missing, "filled": filled, "required": len(fields),
            "completeness": filled / len(fields) if fields else None,
            "complete": len(missing) == 0}
