\set ON_ERROR_STOP on
\i /course/sprint-06-dashboards/project/db/schema_delivery.sql
SET search_path TO delivery, public;
\echo 'Загрузка «Скорохода»...'
COPY cities      FROM '/course/sprint-06-dashboards/project/db/out/cities.csv'      WITH (FORMAT csv, HEADER true, NULL '');
COPY restaurants FROM '/course/sprint-06-dashboards/project/db/out/restaurants.csv' WITH (FORMAT csv, HEADER true, NULL '');
COPY couriers    FROM '/course/sprint-06-dashboards/project/db/out/couriers.csv'    WITH (FORMAT csv, HEADER true, NULL '');
COPY customers   FROM '/course/sprint-06-dashboards/project/db/out/customers.csv'   WITH (FORMAT csv, HEADER true, NULL '');
COPY orders      FROM '/course/sprint-06-dashboards/project/db/out/orders.csv'      WITH (FORMAT csv, HEADER true, NULL '');
COPY order_items FROM '/course/sprint-06-dashboards/project/db/out/order_items.csv' WITH (FORMAT csv, HEADER true, NULL '');
ANALYZE;
SELECT table_name,
       (xpath('/row/c/text()', query_to_xml(
          format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name),
          false, true, '')))[1]::text::bigint AS rows
FROM information_schema.tables
WHERE table_schema = 'delivery' AND table_type = 'BASE TABLE'
ORDER BY rows DESC;
