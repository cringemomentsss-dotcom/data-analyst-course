"""Загрузка открытых данных нью-йоркского такси для дипломного проекта.

Данные настоящие и открытые: регистрация не нужна, лицензия позволяет
использовать их в портфолио.

    python3 projects/diplom/db/download_nyc.py --months 2024-01 2024-02
    python3 projects/diplom/db/download_nyc.py --year 2024        # все 12

Один месяц — около 48 МБ и 3 млн поездок. Год — примерно 570 МБ и
40 млн строк. Проверь, что место на диске есть.

Файлы кладутся в projects/diplom/db/raw/ и в репозиторий не попадают.
"""

import argparse
import os
import sys
import urllib.request

BASE = "https://d37ci6vzurychx.cloudfront.net/trip-data"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")


def download(month, dataset="yellow"):
    name = f"{dataset}_tripdata_{month}.parquet"
    path = os.path.join(OUT, name)
    if os.path.exists(path):
        print(f"{name}: уже есть, пропускаю")
        return path
    url = f"{BASE}/{name}"
    print(f"{name}: качаю...", end=" ", flush=True)
    try:
        urllib.request.urlretrieve(url, path)
    except Exception as exc:
        print(f"не вышло — {exc}")
        return None
    print(f"{os.path.getsize(path) / 1024 / 1024:.0f} МБ")
    return path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--months", nargs="*", help="список вида 2024-01 2024-02")
    p.add_argument("--year", help="скачать все месяцы года")
    p.add_argument("--dataset", default="yellow",
                   choices=["yellow", "green", "fhvhv"],
                   help="yellow — жёлтое такси, green — зелёное, "
                        "fhvhv — агрегаторы (файлы кратно больше)")
    a = p.parse_args()

    if a.year:
        months = [f"{a.year}-{m:02d}" for m in range(1, 13)]
    elif a.months:
        months = a.months
    else:
        p.error("укажи --months или --year")

    os.makedirs(OUT, exist_ok=True)
    ok = [m for m in months if download(m, a.dataset)]
    total = sum(os.path.getsize(os.path.join(OUT, f))
                for f in os.listdir(OUT) if f.endswith(".parquet"))
    print(f"\nскачано файлов: {len(ok)} из {len(months)}")
    print(f"всего в {OUT}: {total / 1024 / 1024:.0f} МБ")
    if len(ok) < len(months):
        print("часть файлов не скачалась: свежие месяцы публикуются "
              "с задержкой примерно в два месяца")
        sys.exit(1)


if __name__ == "__main__":
    main()
