\set ON_ERROR_STOP on
\i /course/sprint-04-okna/project/db/schema_game.sql
SET search_path TO game, public;
\echo 'Загрузка «Секретов Темнолесья»...'
COPY players     FROM '/course/sprint-04-okna/project/db/out/players.csv'     WITH (FORMAT csv, HEADER true, NULL '');
COPY items       FROM '/course/sprint-04-okna/project/db/out/items.csv'       WITH (FORMAT csv, HEADER true, NULL '');
COPY promo_codes FROM '/course/sprint-04-okna/project/db/out/promo_codes.csv' WITH (FORMAT csv, HEADER true, NULL '');
COPY sessions    FROM '/course/sprint-04-okna/project/db/out/sessions.csv'    WITH (FORMAT csv, HEADER true, NULL '');
COPY levels      FROM '/course/sprint-04-okna/project/db/out/levels.csv'      WITH (FORMAT csv, HEADER true, NULL '');
COPY purchases   FROM '/course/sprint-04-okna/project/db/out/purchases.csv'   WITH (FORMAT csv, HEADER true, NULL '');
ANALYZE;
SELECT table_name,
       (xpath('/row/c/text()', query_to_xml(
          format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name),
          false, true, '')))[1]::text::bigint AS rows
FROM information_schema.tables
WHERE table_schema = 'game' AND table_type = 'BASE TABLE'
ORDER BY rows DESC;
