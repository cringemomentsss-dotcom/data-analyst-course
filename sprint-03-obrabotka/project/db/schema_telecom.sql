-- Схема проекта спринта 3: федеральный оператор связи «Мегасеть».
DROP SCHEMA IF EXISTS telecom CASCADE;
CREATE SCHEMA telecom;
SET search_path TO telecom, public;

CREATE TABLE cities (
    city_id    integer PRIMARY KEY,
    city       text NOT NULL,
    region     text NOT NULL,
    population integer NOT NULL,
    utc_offset smallint NOT NULL
);

CREATE TABLE tariffs (
    tariff_id        integer PRIMARY KEY,
    tariff_name      text NOT NULL,
    monthly_fee      numeric(10,2) NOT NULL,
    incl_minutes     integer NOT NULL,
    incl_sms         integer NOT NULL,
    incl_gb          integer NOT NULL,
    price_per_minute numeric(6,2) NOT NULL,
    price_per_sms    numeric(6,2) NOT NULL,
    price_per_gb     numeric(6,2) NOT NULL
);
COMMENT ON TABLE tariffs IS 'Пакет включён в абонплату; сверх пакета тарифицируется поштучно.';

CREATE TABLE clients (
    client_id   integer PRIMARY KEY,
    reg_date    date NOT NULL,
    city_id     integer REFERENCES cities(city_id),
    tariff_id   integer NOT NULL REFERENCES tariffs(tariff_id),
    churn_date  date,
    client_type text NOT NULL
);
COMMENT ON COLUMN clients.churn_date IS 'Дата расторжения договора. NULL — абонент действующий.';
COMMENT ON COLUMN clients.city_id IS 'У части абонентов город не заполнен.';

CREATE TABLE calls (
    call_id      bigint PRIMARY KEY,
    client_id    integer NOT NULL REFERENCES clients(client_id),
    call_ts      timestamp NOT NULL,
    duration_min numeric(6,1) NOT NULL
);
COMMENT ON TABLE calls IS 'Звонки. duration_min = 0 — недозвон. Часть строк задвоена биллингом.';

CREATE TABLE messages (
    message_id   bigint PRIMARY KEY,
    client_id    integer NOT NULL REFERENCES clients(client_id),
    message_ts   timestamp NOT NULL
);

CREATE TABLE internet (
    session_id integer PRIMARY KEY,
    client_id  integer NOT NULL REFERENCES clients(client_id),
    session_ts timestamp NOT NULL,
    mb_used    numeric(10,1) NOT NULL
);

CREATE TABLE tickets (
    ticket_id  integer PRIMARY KEY,
    client_id  integer NOT NULL REFERENCES clients(client_id),
    created_ts timestamp NOT NULL,
    topic      text NOT NULL,
    status     text NOT NULL
);

CREATE INDEX ix_calls_client ON calls(client_id);
CREATE INDEX ix_calls_ts     ON calls(call_ts);
CREATE INDEX ix_msg_client   ON messages(client_id);
CREATE INDEX ix_net_client   ON internet(client_id);
CREATE INDEX ix_cl_tariff    ON clients(tariff_id);
