# База проекта: маркетплейс «Полка»

```bash
make market
```

Поднимает схему `market` в базе `casino`. Не забудь `SET search_path TO market;`.

Витрины выгружаются в CSV для Tableau Public:

```bash
make export SQL=projects/module-02-marketplace/mart_monthly.sql \
            OUT=projects/module-02-marketplace/mart_monthly.csv
```
