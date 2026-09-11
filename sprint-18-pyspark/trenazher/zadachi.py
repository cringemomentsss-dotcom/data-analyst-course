"""
ТРЕНАЖЁР СПРИНТА 18. 18 задач по PySpark.

Задачи на чистом Python: ни Spark, ни Java для тренажёра не нужны.
Это не упрощение. Всё, на чём в Spark ошибаются, — не синтаксис, а модель
исполнения: где план, а где вычисление, где граница стадии, что попадёт
на driver, что перезапишет overwrite. Разобравшись в этом здесь, ты
будешь писать код проекта, понимая, что произойдёт, — а не запуская
и глядя, что получилось.

Spark для проекта поднимается в Docker: make spark.

Проверка:    make test SPRINT=18
Одна задача: python3 -m pytest sprint-18-pyspark/trenazher -q -k shuffle
"""

import math

import numpy as np
import pandas as pd

ACTIONS = {"show", "collect", "count", "take", "first", "head", "write",
           "toPandas", "foreach", "save", "saveAsTable"}

WIDE = {"groupBy", "join", "distinct", "dropDuplicates", "repartition",
        "orderBy", "sort", "reduceByKey", "cogroup", "intersect", "except"}

NARROW = {"select", "filter", "where", "withColumn", "drop", "map",
          "flatMap", "union", "sample", "coalesce", "cast", "alias"}


# === Часть 1. Ленивость и DAG ==============================================

def is_action(op):
    """Действие или трансформация.

    Возвращает {'op', 'kind', 'triggers_execution'} и, для трансформаций,
    ещё 'wide'. Неизвестная операция — ValueError.

    Наборы ACTIONS, WIDE и NARROW уже даны.

    Центральная идея Spark: **трансформация ничего не делает.** Она только
    дописывает шаг в план. Ни одна строка не прочитана, пока не вызвано
    действие. Отсюда следствие, которое сбивает всех, кто пришёл из
    pandas: ошибка в фильтре обнаружится не на строке с фильтром, а
    через двадцать строк, на `show()`.
    """
    raise NotImplementedError


def find_shuffles(ops):
    """Операции из цепочки, вызывающие shuffle.

    Возвращает [{'position', 'op', 'reason'}] по порядку; position —
    индекс в исходном списке.

    Shuffle — перераспределение данных между партициями по сети, с
    записью на диск. Это самая дорогая операция в Spark, и почти всё
    искусство оптимизации сводится к тому, чтобы их было меньше.

    Узкая трансформация (`filter`, `withColumn`) обрабатывает партицию
    независимо от других — данные никуда не едут. Широкая (`groupBy`,
    `join`, `distinct`) требует собрать вместе строки с одинаковым
    ключом, а они лежат в разных партициях на разных машинах.
    """
    raise NotImplementedError


def count_stages(ops):
    """Число стадий выполнения.

    Возвращает {'stages', 'shuffles', 'shuffle_ops', 'executes', 'note'}.

    Стадия — цепочка узких трансформаций, выполняемых без перемешивания.
    Каждая широкая закрывает стадию и открывает следующую, поэтому
    стадий на одну больше, чем shuffle-ов.

    executes — есть ли в цепочке хоть одно действие. Если нет, положи в
    note, что план построен, но ничего не выполнится; при пустом списке
    операций stages равно нулю.

    Число стадий видно в Spark UI, и по нему сразу понятно, во что
    обойдётся запрос. Четыре стадии — это три записи промежуточных
    данных на диск.
    """
    raise NotImplementedError


def build_dag(ops):
    """Разбор цепочки на стадии.

    Возвращает {'stages', 'n_stages', 'actions', 'lazy_until'}.
    stages — список списков операций; широкая трансформация входит в ту
    стадию, которую закрывает. Действия в стадии не входят.
    lazy_until — первое действие в цепочке или None.

    После последней широкой трансформации всегда открывается ещё одна
    стадия, даже если в ней не осталось операций: в ней происходит
    запись результата. Поэтому n_stages обязано совпадать с 'stages'
    из count_stages.
    """
    raise NotImplementedError


# === Часть 2. Схема и форматы ==============================================

TYPE_MAP = {"int": "IntegerType()", "long": "LongType()",
            "float": "FloatType()", "double": "DoubleType()",
            "str": "StringType()", "bool": "BooleanType()",
            "date": "DateType()", "timestamp": "TimestampType()",
            "decimal": "DecimalType(10, 2)"}


def schema_from_spec(spec):
    """Явная схема датафрейма из спецификации {имя: (тип, nullable)}.

    Возвращает строку вида:

        StructType([
            StructField("user_id", LongType(), False),
            StructField("revenue", DecimalType(10, 2), True),
        ])

    Отступ четыре пробела, запятая после каждого поля, включая последнее.
    Неизвестный тип — ValueError.
    """
    raise NotImplementedError


def inference_risks(sample_rows, column):
    """Чем опасен inferSchema для конкретного столбца.

    Возвращает {'column', 'risks', 'safe', 'guessed'}.
    risks — список текстов, safe — их отсутствие, guessed — тип, который
    Spark, скорее всего, выведет.

    Разбирай в таком порядке (пустые строки и None не считаются значениями):

    1. Значений нет вовсе — риск «все значения пусты, тип угадать нельзя»,
       guessed StringType().
    2. Все значения целые: guessed Integer или Long по величине.
       Если у какого-то есть ведущий ноль — риск, что это идентификатор,
       а не число. Если не помещается в 32 бита — отдельный риск.
    3. Все значения числовые с точкой: guessed DoubleType(), риск
       потери точности на деньгах.
    4. Иначе StringType(); если часть значений всё же числовая — риск,
       что тип зависит от того, какие строки попали в выборку.

    И отдельно, поверх всего: если среди исходных значений были пропуски,
    добавь риск про угаданный nullable.

    Почему inference опасен на практике. Spark читает часть файла и
    выводит типы по ней. Завтра приедет файл, где в столбце `zip`
    появится значение с буквой, — и схема поменяется, а пайплайн упадёт
    или, хуже, тихо посчитает не то. **Схему задают явно.** Это первый
    пункт критериев приёмки проекта.
    """
    raise NotImplementedError


def format_choice(rows, columns_used, columns_total, need_human_readable=False,
                  need_append=True):
    """Выбор формата хранения.

    Возвращает {'format', 'reason', 'columnar'}. По порядку:
    нужен человекочитаемый — csv; меньше 100 000 строк и не больше пяти
    столбцов — csv; иначе parquet. В reason для parquet укажи, сколько
    столбцов из скольких читается.

    Parquet — стандарт аналитики по трём причинам сразу: колоночный
    (читаются только нужные столбцы), сжатый, и **несёт схему внутри
    себя** — то есть снимает проблему из предыдущей задачи.
    """
    raise NotImplementedError


def parquet_layout(rows, bytes_per_row, partition_by, cardinalities,
                   target_file_mb=128):
    """Раскладка партиционированной записи.

    Возвращает {'partitions', 'total_mb', 'mb_per_partition', 'files',
    'path_template', 'small_files_problem', 'advice'}.

    Число партиций — произведение кардинальностей столбцов из
    partition_by. Файлов в партиции — не меньше одного, дальше по
    target_file_mb. path_template — 'dt=<dt>/country=<country>'.
    small_files_problem — меньше 16 МБ на партицию.

    Партиционирование в хранилище — это просто вложенные папки с
    именами вида `dt=2026-06-01`. Spark читает имена папок и отсекает
    ненужные, не открывая файлы. Работает это только при фильтре по
    столбцу партиционирования, и только если столбцов немного:
    произведение кардинальностей растёт быстро.
    """
    raise NotImplementedError


# === Часть 3. Оптимизация ==================================================

def broadcast_decision(left_mb, right_mb, threshold_mb=10):
    """Стоит ли рассылать меньшую сторону соединения на все узлы.

    Возвращает {'broadcast', 'side', 'small_mb', 'large_mb', 'strategy',
    'reason'}. side — 'left' или 'right' (при равенстве 'right'),
    когда broadcast имеет смысл, иначе None.
    strategy — 'BroadcastHashJoin' или 'SortMergeJoin'.

    Обычное соединение перемешивает **обе** стороны по ключу. Если одна
    из сторон — справочник на пару мегабайт, дешевле разослать его копию
    каждому исполнителю: тогда shuffle не нужен вовсе.

    Это самая результативная оптимизация в Spark, и в аналитике она
    применима почти всегда: факт большой, измерения маленькие.
    """
    raise NotImplementedError


def partition_plan(current_partitions, target_partitions, rows,
                   cores=8, target_rows_per_partition=1_000_000):
    """repartition или coalesce и сколько партиций брать.

    Возвращает {'op', 'from', 'to', 'recommended', 'causes_shuffle',
    'reason'}. recommended = max(cores, ceil(rows / target_rows_per_partition));
    если target_partitions не задан, берётся recommended.
    op — 'coalesce' при уменьшении, 'repartition' при увеличении,
    'ничего' при равенстве.

    Разница, которую надо помнить: **coalesce не перемешивает**, он
    склеивает соседние партиции. Дёшево, но перекос останется и даже
    усилится. **repartition перемешивает** и раскладывает ровно, но это
    shuffle со всеми его затратами.

    Слишком мало партиций — простаивают ядра. Слишком много — накладные
    расходы на задачу превышают саму задачу.
    """
    raise NotImplementedError


def skew_check(partition_rows, threshold=3.0):
    """Перекос партиций. Пустой вход — None.

    Возвращает {'partitions', 'mean_rows', 'max_rows', 'max_partition',
    'ratio', 'skewed', 'advice'}. ratio — максимум к среднему.

    Перекос — причина, по которой задача «почти закончилась» и висит
    так час: 199 партиций из 200 отработали, одна делает работу за всех.
    Обычно это доминирующее значение ключа: NULL, 'unknown', гостевой
    пользователь, на которого списаны все анонимные события.
    """
    raise NotImplementedError


def cache_decision(reuse_count, size_mb, available_mb, is_expensive=True):
    """Стоит ли кэшировать датафрейм.

    Возвращает {'cache', 'fits', 'reason'} и, когда не помещается,
    ещё 'alternative'. Помещается — не больше 60% доступной памяти.
    По порядку: используется один раз — не кэшировать; не помещается —
    не кэшировать, предложить persist(DISK_ONLY) или Parquet;
    пересчёт дёшев — не кэшировать; иначе кэшировать.

    Кэш в Spark — не бесплатная оптимизация, а размен памяти на
    вычисления. Он вредит, когда: датафрейм используется один раз
    (тогда это чистая трата), не помещается в память (тогда он вытесняет
    сам себя и пересчёт идёт всё равно), или пересчитывается дёшево.
    """
    raise NotImplementedError


def join_strategy(left_mb, right_mb, join_key_sorted=False,
                  broadcast_threshold_mb=10):
    """Какую стратегию соединения выберет Spark.

    Возвращает {'strategy', 'shuffle', 'reason'}.
    Broadcast возможен — BroadcastHashJoin без shuffle. Иначе
    SortMergeJoin: без shuffle, если стороны уже отсортированы по ключу,
    и с shuffle в остальных случаях.
    """
    raise NotImplementedError


# === Часть 4. Запись и идемпотентность =====================================

def write_mode(task, partitioned=False):
    """Режим записи под задачу. Неизвестная задача — ValueError.

    | задача | режим |
    |---|---|
    | 'full_reload' | overwrite |
    | 'incremental' | append |
    | 'reprocess_partition' | overwrite |
    | 'first_write' | errorifexists |
    | 'skip_if_exists' | ignore |

    Возвращает {'mode', 'reason', 'warning', 'idempotent'}; idempotent
    истинно только для overwrite.

    Два предупреждения обязательны, потому что стоят дороже всего:

    - для 'reprocess_partition': нужен `partitionOverwriteMode=dynamic`,
      иначе overwrite снесёт **всю** таблицу, а не только пересчитываемые
      партиции;
    - для 'incremental': append не идемпотентен, повторный запуск
      задвоит данные.
    """
    raise NotImplementedError


def partitioned_write_paths(base_path, partition_values, dynamic=True):
    """Какие пути будут затронуты при партиционированной записи.

    partition_values — список словарей {столбец: значение}.
    Возвращает {'paths', 'n_paths', 'overwrites_everything', 'warning'}.
    Пути вида 'base/dt=2026-06-01', отсортированы, без повторов.
    При dynamic ложном — предупреждение, что снесётся весь base_path.
    """
    raise NotImplementedError


def small_files_check(n_files, total_mb, min_file_mb=16, max_files=10000):
    """Проблема мелких файлов.

    Возвращает {'n_files', 'avg_file_mb', 'ok', 'problems', 'advice'}.

    Тысячи мелких файлов — типичный результат наивной записи и
    отдельная беда объектных хранилищ: на каждый файл нужен запрос
    метаданных, и чтение упирается в них, а не в объём. Правило: файл
    от сотни мегабайт, партиций столько, чтобы это выполнялось.
    """
    raise NotImplementedError


def driver_memory_risk(rows, bytes_per_row, driver_mb, op="collect",
                       max_rows=1_000_000, python_overhead=3.0):
    """Риск положить driver действием, которое тянет данные на него.

    Возвращает {'op', 'rows', 'needed_mb', 'driver_mb', 'fits',
    'too_many_rows', 'safe', 'advice'}.

    needed_mb = rows × bytes_per_row / 1024 / 1024 × python_overhead,
    и ещё вдвое больше для 'toPandas'. fits — не больше половины
    driver_mb. too_many_rows — больше max_rows. safe — и то и другое.

    Две поправки здесь не для красоты. python_overhead: строка в памяти
    Python занимает в разы больше, чем в колоночном файле. max_rows:
    миллионы строк на driver не тянут независимо от их размера — это
    просто не то, для чего он существует.

    `collect()` на большом датафрейме — самая частая причина падения
    Spark-задачи у новичка. Второе место — `toPandas()`, который делает
    то же самое, но выглядит невиннее.
    """
    raise NotImplementedError


def pipeline_idempotent(existing_partitions, new_partitions, mode):
    """Что станет с данными при повторном запуске.

    mode — 'append', 'overwrite_dynamic' или 'overwrite_static',
    иное — ValueError.

    Возвращает {'idempotent', 'duplicated', 'added', 'lost', 'reason'};
    списки отсортированы.

    - append: задвоятся партиции, попавшие в оба набора;
    - overwrite_dynamic: перезапишутся только затронутые, потерь нет;
    - overwrite_static: перезапишется вся таблица, и партиции, которых
      нет в новых данных, **исчезнут**.

    Третий случай — тихая потеря данных, которую замечают через неделю.
    Оба overwrite идемпотентны, но у статического цена — вся история.
    """
    raise NotImplementedError
