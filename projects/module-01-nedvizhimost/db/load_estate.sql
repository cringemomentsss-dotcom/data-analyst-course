\set ON_ERROR_STOP on
\i /course/projects/module-01-nedvizhimost/db/schema_estate.sql
SET search_path TO estate, public;
\echo 'Загрузка объявлений...'
COPY localities FROM '/course/projects/module-01-nedvizhimost/db/out/localities.csv' WITH (FORMAT csv, HEADER true, NULL '');
COPY listings   FROM '/course/projects/module-01-nedvizhimost/db/out/listings.csv'   WITH (FORMAT csv, HEADER true, NULL '');
ANALYZE;
SELECT table_name,
       (xpath('/row/c/text()', query_to_xml(
          format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name),
          false, true, '')))[1]::text::bigint AS rows
FROM information_schema.tables
WHERE table_schema = 'estate' AND table_type = 'BASE TABLE'
ORDER BY rows DESC;
