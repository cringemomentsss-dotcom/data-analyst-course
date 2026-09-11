\set ON_ERROR_STOP on
\i /course/projects/module-04-shop/db/schema_shop.sql
SET search_path TO shop, public;
\echo 'Загрузка BitMotion Kit...'
COPY users          FROM '/course/projects/module-04-shop/db/out/users.csv'          WITH (FORMAT csv, HEADER true, NULL '');
COPY sessions       FROM '/course/projects/module-04-shop/db/out/sessions.csv'       WITH (FORMAT csv, HEADER true, NULL '');
COPY events         FROM '/course/projects/module-04-shop/db/out/events.csv'         WITH (FORMAT csv, HEADER true, NULL '');
COPY orders         FROM '/course/projects/module-04-shop/db/out/orders.csv'         WITH (FORMAT csv, HEADER true, NULL '');
COPY experiment     FROM '/course/projects/module-04-shop/db/out/experiment.csv'     WITH (FORMAT csv, HEADER true, NULL '');
COPY ab_assignments FROM '/course/projects/module-04-shop/db/out/ab_assignments.csv' WITH (FORMAT csv, HEADER true, NULL '');
ANALYZE;
SELECT table_name,
       (xpath('/row/c/text()', query_to_xml(
          format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name),
          false, true, '')))[1]::text::bigint AS rows
FROM information_schema.tables
WHERE table_schema = 'shop' AND table_type = 'BASE TABLE'
ORDER BY rows DESC;
