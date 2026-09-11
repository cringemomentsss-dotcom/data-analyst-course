\set ON_ERROR_STOP on
\i /course/sprint-02-postgres/project/db/schema_stream.sql
SET search_path TO stream, public;
\echo 'Загрузка «Потока»...'
COPY artists         FROM '/course/sprint-02-postgres/project/db/out/artists.csv'         WITH (FORMAT csv, HEADER true, NULL '');
COPY tracks          FROM '/course/sprint-02-postgres/project/db/out/tracks.csv'          WITH (FORMAT csv, HEADER true, NULL '');
COPY users           FROM '/course/sprint-02-postgres/project/db/out/users.csv'           WITH (FORMAT csv, HEADER true, NULL '');
COPY subscriptions   FROM '/course/sprint-02-postgres/project/db/out/subscriptions.csv'   WITH (FORMAT csv, HEADER true, NULL '');
COPY listens         FROM '/course/sprint-02-postgres/project/db/out/listens.csv'         WITH (FORMAT csv, HEADER true, NULL '');
COPY playlists       FROM '/course/sprint-02-postgres/project/db/out/playlists.csv'       WITH (FORMAT csv, HEADER true, NULL '');
COPY playlist_tracks FROM '/course/sprint-02-postgres/project/db/out/playlist_tracks.csv' WITH (FORMAT csv, HEADER true, NULL '');
ANALYZE;
SELECT table_name,
       (xpath('/row/c/text()', query_to_xml(
          format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name),
          false, true, '')))[1]::text::bigint AS rows
FROM information_schema.tables
WHERE table_schema = 'stream' AND table_type = 'BASE TABLE'
ORDER BY rows DESC;
