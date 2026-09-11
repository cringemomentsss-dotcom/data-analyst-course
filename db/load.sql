-- Загрузка сгенерированных CSV в PostgreSQL.
-- Запускается внутри контейнера, где ./db смонтирована как /db.
-- Перед запуском: python3 db/generate.py

\set ON_ERROR_STOP on
\i /db/schema.sql
SET search_path TO casino, public;

\echo 'Загрузка ядра...'
COPY users            FROM '/db/out/users.csv'            WITH (FORMAT csv, HEADER true, NULL '');
COPY games            FROM '/db/out/games.csv'            WITH (FORMAT csv, HEADER true, NULL '');
COPY events           FROM '/db/out/events.csv'           WITH (FORMAT csv, HEADER true, NULL '');
COPY sessions         FROM '/db/out/sessions.csv'         WITH (FORMAT csv, HEADER true, NULL '');
COPY deposits         FROM '/db/out/deposits.csv'         WITH (FORMAT csv, HEADER true, NULL '');
COPY withdrawals      FROM '/db/out/withdrawals.csv'      WITH (FORMAT csv, HEADER true, NULL '');
COPY bets             FROM '/db/out/bets.csv'             WITH (FORMAT csv, HEADER true, NULL '');

\echo 'Загрузка трафика и воронки...'
COPY visitors         FROM '/db/out/visitors.csv'         WITH (FORMAT csv, HEADER true, NULL '');
COPY page_events      FROM '/db/out/page_events.csv'      WITH (FORMAT csv, HEADER true, NULL '');

\echo 'Загрузка экспериментов...'
COPY experiments      FROM '/db/out/experiments.csv'      WITH (FORMAT csv, HEADER true, NULL '');
COPY ab_assignments   FROM '/db/out/ab_assignments.csv'   WITH (FORMAT csv, HEADER true, NULL '');

\echo 'Загрузка платежей, бонусов, поддержки, расходов...'
COPY payment_attempts FROM '/db/out/payment_attempts.csv' WITH (FORMAT csv, HEADER true, NULL '');
COPY bonuses          FROM '/db/out/bonuses.csv'          WITH (FORMAT csv, HEADER true, NULL '');
COPY support_tickets  FROM '/db/out/support_tickets.csv'  WITH (FORMAT csv, HEADER true, NULL '');
COPY marketing_spend  FROM '/db/out/marketing_spend.csv'  WITH (FORMAT csv, HEADER true, NULL '');

ANALYZE;

\echo ''
\echo 'Готово. Строк по таблицам:'
SELECT table_name,
       (xpath('/row/c/text()', query_to_xml(
          format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name),
          false, true, '')))[1]::text::bigint AS rows
FROM information_schema.tables
WHERE table_schema = 'casino' AND table_type = 'BASE TABLE'
ORDER BY rows DESC;
