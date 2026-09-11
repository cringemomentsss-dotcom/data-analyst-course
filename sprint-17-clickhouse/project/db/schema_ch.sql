-- Эталонная схема ClickHouse для проекта спринта 17.
-- Ученик проектирует свою; эта нужна, чтобы получить ориентиры по времени.
-- Не открывать до того, как спроектируешь свою.

CREATE DATABASE IF NOT EXISTS course;

DROP TABLE IF EXISTS course.events;
CREATE TABLE course.events
(
    event_id    UInt64,
    user_id     UInt32,
    event_ts    DateTime,
    event_name  LowCardinality(String),
    session_id  UInt64,
    device      LowCardinality(String),
    country     LowCardinality(String),
    revenue     Decimal(10, 2)          -- вместо Nullable: ноль означает «не было выручки»
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_ts)
ORDER BY (user_id, event_ts);

DROP TABLE IF EXISTS course.orders;
CREATE TABLE course.orders
(
    order_id     UInt64,
    user_id      UInt32,
    created_at   DateTime,
    status       LowCardinality(String),
    total_amount Decimal(12, 2)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(created_at)
ORDER BY (user_id, created_at);

DROP TABLE IF EXISTS course.order_lines;
CREATE TABLE course.order_lines
(
    line_id    UInt64,
    order_id   UInt64,
    product_id UInt32,
    qty        UInt8,
    price      Decimal(10, 2)
)
ENGINE = MergeTree
ORDER BY (order_id, line_id);

DROP TABLE IF EXISTS course.users;
CREATE TABLE course.users
(
    user_id UInt32,
    reg_ts  DateTime,
    country LowCardinality(String),
    device  LowCardinality(String),
    plan    LowCardinality(String)
)
ENGINE = MergeTree
ORDER BY user_id;
