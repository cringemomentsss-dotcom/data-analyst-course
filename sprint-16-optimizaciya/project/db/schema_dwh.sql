-- Схема проекта спринта 16: витрина веб-аналитики «Поток+».
-- Данные генерируются прямо в базе: 8 млн событий, 1,5 млн заказов.
-- CSV намеренно нет — выгрузка такого объёма в репозиторий не кладётся.
--
-- Таблицы созданы БЕЗ индексов, кроме первичных ключей. Это не упущение:
-- добавить нужные индексы и доказать, что они нужны, — часть задания.

DROP SCHEMA IF EXISTS dwh CASCADE;
CREATE SCHEMA dwh;
SET search_path TO dwh, public;

CREATE TABLE users (
    user_id     integer PRIMARY KEY,
    reg_ts      timestamp NOT NULL,
    country     text NOT NULL,
    device      text NOT NULL,
    plan        text NOT NULL          -- free / basic / pro
);

CREATE TABLE products (
    product_id  integer PRIMARY KEY,
    title       text NOT NULL,
    category    text NOT NULL,
    price       numeric(10,2) NOT NULL
);

CREATE TABLE orders (
    order_id     bigint PRIMARY KEY,
    user_id      integer NOT NULL,
    created_at   timestamp NOT NULL,
    status       text NOT NULL,        -- paid / cancelled / refunded
    total_amount numeric(12,2) NOT NULL
);

CREATE TABLE order_lines (
    line_id     bigint PRIMARY KEY,
    order_id    bigint NOT NULL,
    product_id  integer NOT NULL,
    qty         smallint NOT NULL,
    price       numeric(10,2) NOT NULL
);

CREATE TABLE events (
    event_id    bigint PRIMARY KEY,
    user_id     integer NOT NULL,
    event_ts    timestamp NOT NULL,
    event_name  text NOT NULL,
    session_id  bigint NOT NULL,
    device      text NOT NULL,
    country     text NOT NULL,
    revenue     numeric(10,2)
);

COMMENT ON TABLE events IS
  'Факт веб-аналитики. 8 млн строк, полтора года. Растёт по времени — то есть физический порядок строк почти совпадает с порядком по event_ts.';
