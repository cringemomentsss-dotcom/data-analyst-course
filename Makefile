# Окружение курса «Аналитик данных»

DB = docker compose exec -T postgres psql -U analyst -d casino
CH = docker compose exec -T clickhouse clickhouse-client --user analyst --password analyst

.PHONY: up down db stream telecom game delivery estate market shop dwh ch ch-up ch-cli s3 spark spark-sh air air-cli air-logs module6-down export test psql check clean

up:            ## поднять PostgreSQL
	docker compose up -d
	@echo "Ждём готовности базы..."
	@until docker compose exec -T postgres pg_isready -U analyst -d casino >/dev/null 2>&1; do sleep 1; done
	@echo "PostgreSQL готов: localhost:5433, база casino, пользователь analyst"

down:          ## погасить контейнер (данные сохраняются)
	docker compose down

db: up         ## сгенерировать данные и залить в базу
	python3 db/generate.py
	$(DB) -v ON_ERROR_STOP=1 -f /db/load.sql

stream: up     ## база проекта спринта 2 — стриминговый сервис «Поток»
	python3 sprint-02-postgres/project/db/generate_stream.py
	$(DB) -v ON_ERROR_STOP=1 -f /course/sprint-02-postgres/project/db/load_stream.sql

telecom: up    ## база проекта спринта 3 — оператор связи «Мегасеть»
	python3 sprint-03-obrabotka/project/db/generate_telecom.py
	$(DB) -v ON_ERROR_STOP=1 -f /course/sprint-03-obrabotka/project/db/load_telecom.sql

game: up       ## база проекта спринта 4 — игра «Секреты Темнолесья»
	python3 sprint-04-okna/project/db/generate_game.py
	$(DB) -v ON_ERROR_STOP=1 -f /course/sprint-04-okna/project/db/load_game.sql

delivery: up   ## база проекта спринта 6 — доставка еды «Скороход»
	python3 sprint-06-dashboards/project/db/generate_delivery.py
	$(DB) -v ON_ERROR_STOP=1 -f /course/sprint-06-dashboards/project/db/load_delivery.sql

estate: up     ## база итогового проекта модуля 1 — недвижимость
	python3 projects/module-01-nedvizhimost/db/generate_estate.py
	$(DB) -v ON_ERROR_STOP=1 -f /course/projects/module-01-nedvizhimost/db/load_estate.sql

market: up     ## база итогового проекта модуля 2 — маркетплейс «Полка»
	python3 projects/module-02-marketplace/db/generate_market.py
	$(DB) -v ON_ERROR_STOP=1 -f /course/projects/module-02-marketplace/db/load_market.sql

test:          ## проверить решения Python-тренажёра: make test SPRINT=07
	@test -n "$(SPRINT)" || (echo "Укажи SPRINT=07 (или 08, 09)"; exit 1)
	python3 -m pytest sprint-$(SPRINT)-*/trenazher -q

shop: up       ## база итогового проекта модуля 4 — интернет-магазин BitMotion Kit
	python3 projects/module-04-shop/db/generate_shop.py
	$(DB) -v ON_ERROR_STOP=1 -f /course/projects/module-04-shop/db/load_shop.sql

dwh: up        ## база проекта спринта 16 — витрина «Поток+», 8 млн событий (~1,3 ГБ, 2 минуты)
	$(DB) -v ON_ERROR_STOP=1 -f /course/sprint-16-optimizaciya/project/db/schema_dwh.sql
	$(DB) -v ON_ERROR_STOP=1 -f /course/sprint-16-optimizaciya/project/db/load_dwh.sql

ch-up:         ## поднять ClickHouse (модуль 6)
	docker compose --profile module6 up -d clickhouse
	@echo "Ждём готовности ClickHouse..."
	@until docker compose exec -T clickhouse wget -qO- http://127.0.0.1:8123/ping >/dev/null 2>&1; do sleep 1; done
	@echo "ClickHouse готов: HTTP 8123, нативный 9000, база course, пользователь analyst"

ch: ch-up      ## перенести схему dwh в ClickHouse (сначала сделай make dwh)
	$(CH) --multiquery < sprint-17-clickhouse/project/db/schema_ch.sql
	$(CH) --multiquery --receive_timeout 900 < sprint-17-clickhouse/project/db/load_ch.sql
	$(CH) -q "SELECT table, sum(rows) AS rows, formatReadableSize(sum(bytes_on_disk)) AS size \
	  FROM system.parts WHERE database='course' AND active GROUP BY table ORDER BY rows DESC"

ch-cli: ch-up  ## интерактивная консоль ClickHouse
	docker compose exec clickhouse clickhouse-client --user analyst --password analyst

s3:            ## сгенерировать сырые логи и залить в MinIO (модуль 6, ~50 МБ)
	docker compose --profile module6 up -d minio
	@until curl -sf http://localhost:9002/minio/health/live >/dev/null; do sleep 1; done
	python3 sprint-18-pyspark/project/data/generate_logs.py
	docker run --rm -v "$(PWD)/sprint-18-pyspark/project/data/out:/src:ro" \
	  --network da-course_default --entrypoint sh \
	  minio/minio:RELEASE.2024-09-13T20-26-02Z -c \
	  "mc alias set m http://minio:9000 analyst analyst123 >/dev/null && \
	   mc mb --ignore-existing m/raw m/lake >/dev/null && \
	   mc cp --recursive --quiet /src/ m/raw/ && mc ls --recursive m/raw/ | wc -l"
	@echo "Готово. Консоль MinIO: http://localhost:9001 (analyst / analyst123)"

spark:         ## поднять Spark (модуль 6)
	docker compose --profile module6 up -d spark minio
	@echo "Spark готов. Запуск скрипта: make spark-sh CMD='spark-submit /course/путь.py'"

spark-sh: spark ## выполнить команду в контейнере Spark: make spark-sh CMD='...'
	@test -n "$(CMD)" || (echo "Укажи CMD='spark-submit /course/...py'"; exit 1)
	docker compose exec -T spark bash -lc '$(CMD)'

air:           ## поднять Airflow (модуль 6), UI на localhost:8080
	docker compose --profile module6 up -d airflow
	@echo "Ждём Airflow..."
	@until curl -sf http://localhost:8080/health >/dev/null 2>&1; do sleep 2; done
	@echo "Airflow готов: http://localhost:8080 (analyst / analyst)"

air-cli: air   ## команда в Airflow: make air-cli CMD='dags list'
	@test -n "$(CMD)" || (echo "Укажи CMD='dags list'"; exit 1)
	docker compose exec -T airflow airflow $(CMD)

air-logs:      ## последние строки лога Airflow
	docker compose logs --tail 60 airflow

module6-down:  ## погасить всё окружение модуля 6 (данные сохраняются)
	docker compose --profile module6 stop airflow spark clickhouse minio

export: up     ## выгрузить витрину в CSV для Tableau: make export SQL=... OUT=...
	@test -n "$(SQL)" || (echo "Укажи SQL=путь/к/запросу.sql и OUT=путь/к/файлу.csv"; exit 1)
	@test -n "$(OUT)" || (echo "Укажи OUT=путь/к/файлу.csv"; exit 1)
	python3 tools/export_csv.py "$(SQL)" "$(OUT)"

psql: up       ## интерактивная консоль
	docker compose exec postgres psql -U analyst -d casino

check: up      ## быстрая проверка, что база на месте
	$(DB) -c "\\dt casino.*"
	$(DB) -c "SET search_path TO casino; \
	  SELECT 'users' t, count(*) FROM users UNION ALL \
	  SELECT 'visitors', count(*) FROM visitors UNION ALL \
	  SELECT 'page_events', count(*) FROM page_events UNION ALL \
	  SELECT 'bets', count(*) FROM bets ORDER BY 1;"

clean:         ## снести базу вместе с данными
	docker compose down -v
