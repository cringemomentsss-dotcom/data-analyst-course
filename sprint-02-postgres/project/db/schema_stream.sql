-- Схема проекта спринта 2: музыкальный стриминговый сервис «Поток».
DROP SCHEMA IF EXISTS stream CASCADE;
CREATE SCHEMA stream;
SET search_path TO stream, public;

CREATE TABLE artists (
    artist_id   integer PRIMARY KEY,
    artist_name text NOT NULL,
    genre       text NOT NULL,
    country     text
);
COMMENT ON TABLE artists IS 'Исполнители.';

CREATE TABLE tracks (
    track_id     integer PRIMARY KEY,
    artist_id    integer NOT NULL REFERENCES artists(artist_id),
    title        text NOT NULL,
    duration_sec integer NOT NULL,
    release_date date NOT NULL,
    is_explicit  smallint NOT NULL
);
COMMENT ON TABLE tracks IS 'Треки. Одна строка — один трек.';

CREATE TABLE users (
    user_id     integer PRIMARY KEY,
    signup_date date NOT NULL,
    country     text,
    plan        text NOT NULL,   -- free / individual / duo / family
    age_group   text NOT NULL
);
COMMENT ON TABLE users IS 'Слушатели. plan — текущий тариф.';

CREATE TABLE subscriptions (
    sub_id     integer PRIMARY KEY,
    user_id    integer NOT NULL REFERENCES users(user_id),
    plan       text NOT NULL,
    started_at timestamp NOT NULL,
    ended_at   timestamp,        -- NULL — подписка активна
    price_eur  numeric(6,2) NOT NULL,
    status     text NOT NULL     -- active / churned / paused
);
COMMENT ON TABLE subscriptions IS 'Платные подписки. У free-пользователей строк нет.';

CREATE TABLE listens (
    listen_id   bigint PRIMARY KEY,
    user_id     integer NOT NULL REFERENCES users(user_id),
    track_id    integer NOT NULL REFERENCES tracks(track_id),
    listened_at timestamp NOT NULL,
    ms_played   integer NOT NULL,
    device      text NOT NULL,
    source      text NOT NULL    -- playlist / search / radio / album
);
COMMENT ON TABLE listens IS 'Прослушивания. ms_played — сколько миллисекунд реально проиграно.';
COMMENT ON COLUMN listens.ms_played IS 'У части строк превышает длительность трека — баг клиента, не данные.';

CREATE TABLE playlists (
    playlist_id integer PRIMARY KEY,
    user_id     integer NOT NULL REFERENCES users(user_id),
    title       text NOT NULL,
    created_at  timestamp NOT NULL,
    is_public   smallint NOT NULL
);

CREATE TABLE playlist_tracks (
    playlist_id integer NOT NULL REFERENCES playlists(playlist_id),
    track_id    integer NOT NULL REFERENCES tracks(track_id),
    added_at    timestamp NOT NULL
);
COMMENT ON TABLE playlist_tracks IS 'Связь плейлистов и треков. Первичного ключа нет: один трек попадает в плейлист дважды.';

CREATE INDEX ix_listens_user  ON listens(user_id);
CREATE INDEX ix_listens_track ON listens(track_id);
CREATE INDEX ix_listens_at    ON listens(listened_at);
CREATE INDEX ix_tracks_artist ON tracks(artist_id);
CREATE INDEX ix_subs_user     ON subscriptions(user_id);
CREATE INDEX ix_pt_playlist   ON playlist_tracks(playlist_id);
