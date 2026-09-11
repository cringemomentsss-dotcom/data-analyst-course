\set ON_ERROR_STOP on
\i /course/sprint-03-obrabotka/project/db/schema_telecom.sql
SET search_path TO telecom, public;
\echo 'Загрузка «Мегасети»...'
COPY cities   FROM '/course/sprint-03-obrabotka/project/db/out/cities.csv'   WITH (FORMAT csv, HEADER true, NULL '');
COPY tariffs  FROM '/course/sprint-03-obrabotka/project/db/out/tariffs.csv'  WITH (FORMAT csv, HEADER true, NULL '');
COPY clients  FROM '/course/sprint-03-obrabotka/project/db/out/clients.csv'  WITH (FORMAT csv, HEADER true, NULL '');
COPY calls    FROM '/course/sprint-03-obrabotka/project/db/out/calls.csv'    WITH (FORMAT csv, HEADER true, NULL '');
COPY messages FROM '/course/sprint-03-obrabotka/project/db/out/messages.csv' WITH (FORMAT csv, HEADER true, NULL '');
COPY internet FROM '/course/sprint-03-obrabotka/project/db/out/internet.csv' WITH (FORMAT csv, HEADER true, NULL '');
COPY tickets  FROM '/course/sprint-03-obrabotka/project/db/out/tickets.csv'  WITH (FORMAT csv, HEADER true, NULL '');
ANALYZE;
SELECT table_name,
       (xpath('/row/c/text()', query_to_xml(
          format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name),
          false, true, '')))[1]::text::bigint AS rows
FROM information_schema.tables
WHERE table_schema = 'telecom' AND table_type = 'BASE TABLE'
ORDER BY rows DESC;
