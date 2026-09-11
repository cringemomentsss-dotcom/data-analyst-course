-- Схема проекта спринта 4: онлайн-игра «Секреты Темнолесья».
DROP SCHEMA IF EXISTS game CASCADE;
CREATE SCHEMA game;
SET search_path TO game, public;

CREATE TABLE players (
    player_id integer PRIMARY KEY,
    reg_date  date NOT NULL,
    country   text,
    platform  text NOT NULL,   -- ios / android / pc
    channel   text NOT NULL    -- канал привлечения
);

CREATE TABLE items (
    item_id    integer PRIMARY KEY,
    item_name  text NOT NULL,
    category   text NOT NULL,  -- cosmetic / booster / currency / battlepass / bundle
    rarity     text NOT NULL,  -- common / rare / epic / legendary
    base_price numeric(8,2) NOT NULL
);

CREATE TABLE promo_codes (
    code         text PRIMARY KEY,
    discount_pct smallint NOT NULL,
    valid_from   date NOT NULL,
    valid_to     date NOT NULL
);
COMMENT ON TABLE promo_codes IS 'Сроки действия промокодов. Часть покупок сделана вне срока — это баг.';

CREATE TABLE sessions (
    session_id   integer PRIMARY KEY,
    player_id    integer NOT NULL REFERENCES players(player_id),
    started_at   timestamp NOT NULL,
    duration_min numeric(7,1) NOT NULL,
    level_start  integer NOT NULL,
    level_end    integer NOT NULL,
    platform     text NOT NULL
);

CREATE TABLE levels (
    player_id  integer NOT NULL REFERENCES players(player_id),
    level      integer NOT NULL,
    reached_at timestamp NOT NULL
);
COMMENT ON TABLE levels IS 'Прогресс по уровням. Первичного ключа нет намеренно.';

CREATE TABLE purchases (
    purchase_id integer PRIMARY KEY,
    player_id   integer NOT NULL REFERENCES players(player_id),
    item_id     integer NOT NULL REFERENCES items(item_id),
    purchase_ts timestamp NOT NULL,
    price_paid  numeric(8,2) NOT NULL,
    promo_code  text,
    status      text NOT NULL   -- paid / refunded
);
COMMENT ON COLUMN purchases.status IS 'refunded — покупка возвращена, в выручку не входит.';

CREATE INDEX ix_g_sess_player ON sessions(player_id);
CREATE INDEX ix_g_sess_at     ON sessions(started_at);
CREATE INDEX ix_g_pur_player  ON purchases(player_id);
CREATE INDEX ix_g_pur_ts      ON purchases(purchase_ts);
CREATE INDEX ix_g_lvl_player  ON levels(player_id);
