\set ON_ERROR_STOP on
\i /course/projects/module-02-marketplace/db/schema_market.sql
SET search_path TO market, public;
\echo 'Загрузка «Полки»...'
COPY categories  FROM '/course/projects/module-02-marketplace/db/out/categories.csv'  WITH (FORMAT csv, HEADER true, NULL '');
COPY sellers     FROM '/course/projects/module-02-marketplace/db/out/sellers.csv'     WITH (FORMAT csv, HEADER true, NULL '');
COPY products    FROM '/course/projects/module-02-marketplace/db/out/products.csv'    WITH (FORMAT csv, HEADER true, NULL '');
COPY buyers      FROM '/course/projects/module-02-marketplace/db/out/buyers.csv'      WITH (FORMAT csv, HEADER true, NULL '');
COPY orders      FROM '/course/projects/module-02-marketplace/db/out/orders.csv'      WITH (FORMAT csv, HEADER true, NULL '');
COPY order_lines FROM '/course/projects/module-02-marketplace/db/out/order_lines.csv' WITH (FORMAT csv, HEADER true, NULL '');
COPY returns     FROM '/course/projects/module-02-marketplace/db/out/returns.csv'     WITH (FORMAT csv, HEADER true, NULL '');
COPY reviews     FROM '/course/projects/module-02-marketplace/db/out/reviews.csv'     WITH (FORMAT csv, HEADER true, NULL '');
ANALYZE;
SELECT table_name,
       (xpath('/row/c/text()', query_to_xml(
          format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name),
          false, true, '')))[1]::text::bigint AS rows
FROM information_schema.tables
WHERE table_schema = 'market' AND table_type = 'BASE TABLE'
ORDER BY rows DESC;
