"""Демонстрационный DAG: показывает механику, не решает проект.

Три вещи, ради которых он здесь:
  1. TaskFlow API — современный способ писать задачи;
  2. логическая дата как параметр обработки, а не datetime.now();
  3. настройки надёжности, которые ставят всегда.

Свой DAG для проекта пиши рядом, этот не трогай.
"""

from datetime import datetime, timedelta

from airflow.decorators import dag, task

DEFAULT_ARGS = {
    "owner": "analyst",
    "retries": 3,
    "retry_delay": timedelta(minutes=1),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
}


@dag(
    dag_id="demo_taskflow",
    schedule="@daily",
    start_date=datetime(2026, 6, 1),
    catchup=False,          # иначе при включении создастся запуск за каждый день
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["demo", "sprint-19"],
    doc_md=__doc__,
)
def demo_taskflow():

    @task
    def pick_partition(ds: str = None) -> str:
        """Берём ЛОГИЧЕСКУЮ дату запуска, а не сегодняшнюю.

        Airflow подставляет `ds` сам: TaskFlow смотрит на имена
        параметров и подставляет одноимённые ключи контекста.
        Значение по умолчанию обязательно — без него Airflow считает
        параметр обязательным аргументом задачи и падает при разборе.

        datetime.now() здесь сделал бы перезапуск за прошлый день
        обработкой сегодняшнего — и никто бы этого не заметил.
        """
        print(f"обрабатываем партицию dt={ds}")
        return ds

    @task
    def count_rows(partition: str) -> int:
        """Заглушка вместо настоящей обработки.

        Параметр называется `partition`, а не `ds`, намеренно. Имя `ds`
        совпало бы с ключом контекста, Airflow подставил бы ему значение
        по умолчанию — и следующий обязательный аргумент сломал бы
        подпись задачи. Ошибка при разборе выглядит так:
        `non-default argument follows default argument`.
        """
        print(f"считаем строки за {partition}")
        return 42

    @task
    def report(partition: str, rows: int) -> None:
        print(f"за {partition} обработано строк: {rows}")

    partition = pick_partition()
    rows = count_rows(partition)
    report(partition, rows)


demo_taskflow()
