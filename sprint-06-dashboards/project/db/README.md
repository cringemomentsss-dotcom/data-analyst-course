# База проекта: «Скороход»

```bash
make delivery
```

Поднимает схему `delivery` в базе `casino`. Не забудь `SET search_path TO delivery;`.

Tableau Public к базе не подключается — витрина выгружается в CSV:

```bash
make export SQL=sprint-06-dashboards/project/mart_daily.sql OUT=sprint-06-dashboards/project/mart_daily.csv
```
