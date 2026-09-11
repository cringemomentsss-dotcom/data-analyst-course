"""Эталонные решения тренажёра спринта 18. Не подглядывать до решения."""

import math

import numpy as np
import pandas as pd

ACTIONS = {"show", "collect", "count", "take", "first", "head", "write",
           "toPandas", "foreach", "save", "saveAsTable"}

WIDE = {"groupBy", "join", "distinct", "dropDuplicates", "repartition",
        "orderBy", "sort", "reduceByKey", "cogroup", "intersect", "except"}

NARROW = {"select", "filter", "where", "withColumn", "drop", "map",
          "flatMap", "union", "sample", "coalesce", "cast", "alias"}


# --- ленивость и DAG -------------------------------------------------------

def is_action(op):
    """Действие или трансформация. Неизвестная операция — ValueError."""
    if op in ACTIONS:
        return {"op": op, "kind": "action", "triggers_execution": True}
    if op in WIDE:
        return {"op": op, "kind": "transformation", "wide": True,
                "triggers_execution": False}
    if op in NARROW:
        return {"op": op, "kind": "transformation", "wide": False,
                "triggers_execution": False}
    raise ValueError(f"неизвестная операция: {op}")


def find_shuffles(ops):
    """Операции, вызывающие shuffle, с позициями."""
    out = []
    for i, op in enumerate(ops):
        if op in WIDE:
            out.append({"position": i, "op": op,
                        "reason": "широкая трансформация: данные "
                                  "перераспределяются между партициями"})
    return out


def count_stages(ops):
    """Число стадий выполнения: границы проходят по shuffle.

    Стадия — цепочка узких трансформаций, выполняемых без перемешивания.
    Каждая широкая трансформация закрывает стадию и открывает следующую.
    """
    shuffles = [o for o in ops if o in WIDE]
    has_action = any(o in ACTIONS for o in ops)
    stages = len(shuffles) + 1 if (ops and has_action) else (
        len(shuffles) + 1 if ops else 0)
    return {"stages": stages, "shuffles": len(shuffles),
            "shuffle_ops": shuffles,
            "executes": has_action,
            "note": "" if has_action else
                    "действия нет — план построен, но ничего не выполнится"}


def build_dag(ops):
    """Разбор цепочки операций на стадии."""
    stages, current = [], []
    for op in ops:
        if op in ACTIONS:
            continue
        current.append(op)
        if op in WIDE:
            stages.append(current)
            current = []
    stages.append(current)
    actions = [o for o in ops if o in ACTIONS]
    return {"stages": stages, "n_stages": len(stages),
            "actions": actions, "lazy_until": actions[0] if actions else None}


# --- схема и форматы -------------------------------------------------------

TYPE_MAP = {"int": "IntegerType()", "long": "LongType()",
            "float": "FloatType()", "double": "DoubleType()",
            "str": "StringType()", "bool": "BooleanType()",
            "date": "DateType()", "timestamp": "TimestampType()",
            "decimal": "DecimalType(10, 2)"}


def schema_from_spec(spec):
    """Явная схема датафрейма из спецификации {имя: (тип, nullable)}."""
    fields = []
    for name, (t, nullable) in spec.items():
        if t not in TYPE_MAP:
            raise ValueError(f"неизвестный тип: {t}")
        fields.append(f'    StructField("{name}", {TYPE_MAP[t]}, {bool(nullable)}),')
    body = "\n".join(fields)
    return "StructType([\n" + body + "\n])"


def inference_risks(sample_rows, column):
    """Чем опасен inferSchema для конкретного столбца."""
    vals = [v for v in sample_rows if v is not None and v != ""]
    risks = []
    if not vals:
        return {"column": column, "risks": ["все значения пусты — тип угадать нельзя"],
                "safe": False, "guessed": "StringType()"}

    def looks_int(v):
        s = str(v).strip()
        return s.lstrip("-").isdigit()

    ints = [v for v in vals if looks_int(v)]
    if ints and len(ints) == len(vals):
        guessed = "IntegerType()" if max(abs(int(str(v))) for v in vals) < 2**31 else "LongType()"
        if any(str(v).strip().startswith("0") and len(str(v).strip()) > 1 for v in vals):
            risks.append("ведущие нули потеряются: это идентификатор, а не число")
        if max(abs(int(str(v))) for v in vals) >= 2**31:
            risks.append("значения не помещаются в 32 бита")
    elif all(str(v).count(".") <= 1 and str(v).replace(".", "").replace("-", "").isdigit()
             for v in vals):
        guessed = "DoubleType()"
        risks.append("деньги во Float теряют точность: нужен Decimal")
    else:
        guessed = "StringType()"
        if ints:
            risks.append("часть значений числовая, часть нет — "
                         "тип зависит от того, какие строки попали в выборку")
    if len(sample_rows) != len(vals):
        risks.append("есть пропуски: nullable будет угадан по выборке")
    return {"column": column, "risks": risks, "safe": len(risks) == 0,
            "guessed": guessed}


def format_choice(rows, columns_used, columns_total, need_human_readable=False,
                  need_append=True):
    """Выбор формата хранения."""
    if need_human_readable:
        return {"format": "csv", "reason": "нужен человекочитаемый файл; "
                "за это платим размером и отсутствием схемы",
                "columnar": False}
    if rows < 100_000 and columns_total <= 5:
        return {"format": "csv", "reason": "мелкий плоский файл: накладные "
                "расходы Parquet не окупятся", "columnar": False}
    share = columns_used / columns_total if columns_total else 1.0
    return {"format": "parquet",
            "reason": f"колоночный формат читает {columns_used} столбцов из "
                      f"{columns_total} ({share:.0%}), несёт схему и сжат",
            "columnar": True}


def parquet_layout(rows, bytes_per_row, partition_by, cardinalities,
                   target_file_mb=128):
    """Раскладка партиционированной записи и оценка числа файлов."""
    parts = 1
    for c in partition_by:
        parts *= max(1, cardinalities.get(c, 1))
    total_mb = rows * bytes_per_row / 1024 / 1024
    per_part_mb = total_mb / parts if parts else total_mb
    files = parts * max(1, math.ceil(per_part_mb / target_file_mb))
    path = "/".join(f"{c}=<{c}>" for c in partition_by)
    return {"partitions": parts, "total_mb": total_mb,
            "mb_per_partition": per_part_mb, "files": files,
            "path_template": path,
            "small_files_problem": per_part_mb < 16,
            "advice": "партиций слишком много: файлы получатся мелкими, "
                      "убери столбец из partitionBy" if per_part_mb < 16
                      else "раскладка разумная"}


# --- оптимизация -----------------------------------------------------------

def broadcast_decision(left_mb, right_mb, threshold_mb=10):
    """Стоит ли рассылать меньшую сторону соединения на все узлы."""
    small, large = min(left_mb, right_mb), max(left_mb, right_mb)
    side = "right" if right_mb <= left_mb else "left"
    if small <= threshold_mb:
        return {"broadcast": True, "side": side, "small_mb": small,
                "large_mb": large,
                "strategy": "BroadcastHashJoin",
                "reason": f"меньшая сторона {small} МБ помещается в память "
                          f"каждого исполнителя — shuffle не нужен"}
    return {"broadcast": False, "side": None, "small_mb": small,
            "large_mb": large, "strategy": "SortMergeJoin",
            "reason": f"меньшая сторона {small} МБ больше порога "
                      f"{threshold_mb} МБ: обе стороны придётся перемешать"}


def partition_plan(current_partitions, target_partitions, rows,
                   cores=8, target_rows_per_partition=1_000_000):
    """repartition или coalesce и сколько партиций брать."""
    recommended = max(cores, math.ceil(rows / target_rows_per_partition))
    if target_partitions is None:
        target_partitions = recommended
    if target_partitions < current_partitions:
        op, shuffle = "coalesce", False
        reason = ("уменьшение без перемешивания: партиции склеиваются. "
                  "Дёшево, но может остаться перекос")
    elif target_partitions > current_partitions:
        op, shuffle = "repartition", True
        reason = "увеличение возможно только через перемешивание"
    else:
        op, shuffle = "ничего", False
        reason = "число партиций уже целевое"
    return {"op": op, "from": current_partitions, "to": target_partitions,
            "recommended": recommended, "causes_shuffle": shuffle,
            "reason": reason}


def skew_check(partition_rows, threshold=3.0):
    """Перекос партиций: одна делает работу за всех."""
    x = np.array(list(partition_rows), dtype=float)
    if len(x) == 0:
        return None
    mean, mx = float(x.mean()), float(x.max())
    ratio = mx / mean if mean else None
    idx = int(np.argmax(x))
    return {"partitions": int(len(x)), "mean_rows": mean, "max_rows": mx,
            "max_partition": idx, "ratio": ratio,
            "skewed": bool(ratio is not None and ratio >= threshold),
            "advice": "перекос: посмотри ключ соединения или группировки, "
                      "скорее всего в нём есть доминирующее значение"
                      if ratio and ratio >= threshold else "распределение ровное"}


def cache_decision(reuse_count, size_mb, available_mb, is_expensive=True):
    """Стоит ли кэшировать датафрейм."""
    fits = size_mb <= available_mb * 0.6
    if reuse_count <= 1:
        return {"cache": False, "fits": fits,
                "reason": "используется один раз: кэш только займёт память"}
    if not fits:
        return {"cache": False, "fits": False,
                "reason": f"{size_mb} МБ не помещается в {available_mb} МБ: "
                          "кэш вытеснит сам себя и пересчёт пойдёт всё равно",
                "alternative": "persist(DISK_ONLY) или запись в Parquet"}
    if not is_expensive:
        return {"cache": False, "fits": True,
                "reason": "пересчёт дёшев: кэшировать нечего"}
    return {"cache": True, "fits": True,
            "reason": f"переиспользуется {reuse_count} раза и дорого считается"}


def join_strategy(left_mb, right_mb, join_key_sorted=False,
                  broadcast_threshold_mb=10):
    """Какую стратегию соединения выберет Spark."""
    b = broadcast_decision(left_mb, right_mb, broadcast_threshold_mb)
    if b["broadcast"]:
        return {"strategy": "BroadcastHashJoin", "shuffle": False,
                "reason": b["reason"]}
    if join_key_sorted:
        return {"strategy": "SortMergeJoin", "shuffle": False,
                "reason": "обе стороны уже отсортированы по ключу — "
                          "перемешивание не требуется"}
    return {"strategy": "SortMergeJoin", "shuffle": True,
            "reason": "обе стороны большие: shuffle по ключу, затем сортировка "
                      "и слияние"}


# --- запись и идемпотентность ----------------------------------------------

def write_mode(task, partitioned=False):
    """Режим записи под задачу."""
    modes = {
        "full_reload": ("overwrite", "витрина пересчитывается целиком"),
        "incremental": ("append", "дописывание новых данных"),
        "reprocess_partition": ("overwrite", "перезапись отдельных партиций"),
        "first_write": ("errorifexists", "защита от перезаписи существующего"),
        "skip_if_exists": ("ignore", "не трогать, если данные уже есть"),
    }
    if task not in modes:
        raise ValueError(f"неизвестная задача: {task}")
    mode, reason = modes[task]
    warning = ""
    if task == "reprocess_partition":
        warning = ("нужен partitionOverwriteMode=dynamic, иначе overwrite "
                   "снесёт ВСЮ таблицу, а не только пересчитываемые партиции")
    if task == "incremental":
        warning = ("append не идемпотентен: повторный запуск задвоит данные. "
                   "Идемпотентность даёт только перезапись партиции целиком")
    return {"mode": mode, "reason": reason, "warning": warning,
            "idempotent": mode == "overwrite"}


def partitioned_write_paths(base_path, partition_values, dynamic=True):
    """Какие пути будут затронуты при партиционированной записи."""
    paths = []
    for row in partition_values:
        suffix = "/".join(f"{k}={v}" for k, v in row.items())
        paths.append(f"{base_path.rstrip('/')}/{suffix}")
    paths = sorted(set(paths))
    return {"paths": paths, "n_paths": len(paths),
            "overwrites_everything": not dynamic,
            "warning": "" if dynamic else
                       f"static overwrite снесёт весь {base_path}, а не только "
                       f"перечисленные партиции"}


def small_files_check(n_files, total_mb, min_file_mb=16, max_files=10000):
    """Проблема мелких файлов."""
    avg = total_mb / n_files if n_files else 0.0
    problems = []
    if avg < min_file_mb:
        problems.append(f"средний файл {avg:.1f} МБ при пороге {min_file_mb}")
    if n_files > max_files:
        problems.append(f"{n_files} файлов — метаданные станут узким местом")
    return {"n_files": int(n_files), "avg_file_mb": avg,
            "ok": len(problems) == 0, "problems": problems,
            "advice": "уменьши число партиций перед записью через coalesce"
                      if problems else "раскладка разумная"}


def driver_memory_risk(rows, bytes_per_row, driver_mb, op="collect",
                       max_rows=1_000_000, python_overhead=3.0):
    """Риск положить driver действием, которое тянет данные на него.

    Учитывает две вещи: объём в памяти driver (он в разы больше, чем на
    диске) и само число строк.
    """
    needed_mb = rows * bytes_per_row / 1024 / 1024 * python_overhead
    if op == "toPandas":
        needed_mb *= 2.0
    fits = needed_mb <= driver_mb * 0.5
    too_many = rows > max_rows
    safe = fits and not too_many
    if safe:
        advice = "безопасно"
    elif too_many:
        advice = (f"{rows} строк на driver — так не делают независимо от "
                  "объёма: используй write, take(n) или агрегируй до collect")
    else:
        advice = (f"{needed_mb:.0f} МБ не влезет в driver на {driver_mb} МБ: "
                  "используй write, take(n) или агрегируй до collect")
    return {"op": op, "rows": int(rows), "needed_mb": needed_mb,
            "driver_mb": driver_mb, "fits": fits, "too_many_rows": too_many,
            "safe": safe, "advice": advice}


def pipeline_idempotent(existing_partitions, new_partitions, mode):
    """Что станет с данными при повторном запуске."""
    ex, new = set(existing_partitions), set(new_partitions)
    if mode == "append":
        return {"idempotent": False, "duplicated": sorted(ex & new),
                "added": sorted(new - ex), "lost": [],
                "reason": "append дописывает поверх существующего"}
    if mode == "overwrite_dynamic":
        return {"idempotent": True, "duplicated": [],
                "added": sorted(new - ex), "lost": [],
                "reason": "перезаписываются только затронутые партиции"}
    if mode == "overwrite_static":
        return {"idempotent": True, "duplicated": [],
                "added": sorted(new - ex), "lost": sorted(ex - new),
                "reason": "перезаписывается вся таблица: партиции, которых нет "
                          "в новых данных, исчезнут"}
    raise ValueError(f"неизвестный режим: {mode}")
