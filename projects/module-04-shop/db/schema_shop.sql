-- Схема итогового проекта модуля 4: интернет-магазин BitMotion Kit.
DROP SCHEMA IF EXISTS shop CASCADE;
CREATE SCHEMA shop;
SET search_path TO shop, public;

CREATE TABLE users (
    user_id   integer PRIMARY KEY,
    signup_ts timestamp NOT NULL,
    country   text,
    device    text NOT NULL,
    channel   text NOT NULL
);

CREATE TABLE sessions (
    session_id   integer PRIMARY KEY,
    user_id      integer NOT NULL REFERENCES users(user_id),
    started_at   timestamp NOT NULL,
    duration_sec integer NOT NULL,
    device       text NOT NULL
);
COMMENT ON COLUMN sessions.duration_sec IS 'Нулевая длительность — сессия не состоялась.';

CREATE TABLE events (
    event_id   integer PRIMARY KEY,
    user_id    integer NOT NULL REFERENCES users(user_id),
    event_ts   timestamp NOT NULL,
    event_name text NOT NULL,   -- view_item / add_to_cart / checkout_start / purchase
    category   text
);
COMMENT ON TABLE events IS 'Воронка. Часть событий задвоена трекером.';

CREATE TABLE orders (
    order_id    integer PRIMARY KEY,
    user_id     integer NOT NULL REFERENCES users(user_id),
    created_at  timestamp NOT NULL,
    revenue     numeric(10,2) NOT NULL,
    items_count smallint NOT NULL,
    status      text NOT NULL   -- delivered / cancelled / returned
);
COMMENT ON TABLE orders IS 'Заказы. Есть задвоенные. Отменённые и возвращённые в выручку не входят.';

CREATE TABLE experiment (
    experiment_id  text PRIMARY KEY,
    name           text NOT NULL,
    hypothesis     text NOT NULL,
    unit           text NOT NULL,
    primary_metric text NOT NULL,
    start_date     date NOT NULL,
    end_date       date NOT NULL,
    planned_split  text NOT NULL,
    status         text NOT NULL
);

CREATE TABLE ab_assignments (
    user_id     integer PRIMARY KEY REFERENCES users(user_id),
    variant     text NOT NULL,   -- control / treatment
    assigned_ts timestamp NOT NULL
);

CREATE INDEX ix_s_sess_user  ON sessions(user_id);
CREATE INDEX ix_s_sess_at    ON sessions(started_at);
CREATE INDEX ix_s_ev_user    ON events(user_id);
CREATE INDEX ix_s_ev_name    ON events(event_name);
CREATE INDEX ix_s_ev_ts      ON events(event_ts);
CREATE INDEX ix_s_ord_user   ON orders(user_id);
CREATE INDEX ix_s_ord_at     ON orders(created_at);
CREATE INDEX ix_s_ab_variant ON ab_assignments(variant);
