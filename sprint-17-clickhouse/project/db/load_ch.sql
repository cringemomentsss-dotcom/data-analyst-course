-- Загрузка из PostgreSQL напрямую, без промежуточных CSV.
-- Функция postgresql() ходит в соседний контейнер по имени сервиса.

INSERT INTO course.events
SELECT event_id, user_id, event_ts, event_name, session_id, device, country,
       ifNull(revenue, 0)
FROM postgresql('postgres:5432', 'casino', 'events', 'analyst', 'analyst', 'dwh');

INSERT INTO course.orders
SELECT order_id, user_id, created_at, status, total_amount
FROM postgresql('postgres:5432', 'casino', 'orders', 'analyst', 'analyst', 'dwh');

INSERT INTO course.order_lines
SELECT line_id, order_id, product_id, qty, price
FROM postgresql('postgres:5432', 'casino', 'order_lines', 'analyst', 'analyst', 'dwh');

INSERT INTO course.users
SELECT user_id, reg_ts, country, device, plan
FROM postgresql('postgres:5432', 'casino', 'users', 'analyst', 'analyst', 'dwh');

OPTIMIZE TABLE course.events FINAL;
