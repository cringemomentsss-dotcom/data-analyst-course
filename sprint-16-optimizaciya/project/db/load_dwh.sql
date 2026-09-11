-- Генерация данных схемы dwh. Детерминированно: setseed фиксирует случайность.
SET search_path TO dwh, public;
SELECT setseed(0.42);

\echo 'users...'
INSERT INTO users
SELECT g,
       timestamp '2025-01-01' + (random() * 540) * interval '1 day',
       (ARRAY['GE','AM','TR','DE','PL','RS'])[1 + floor(random()*6)::int],
       (ARRAY['ios','android','web'])[1 + floor(random()*3)::int],
       (ARRAY['free','free','free','basic','pro'])[1 + floor(random()*5)::int]
FROM generate_series(1, 200000) g;

\echo 'products...'
INSERT INTO products
SELECT g,
       'Товар ' || g,
       (ARRAY['электроника','одежда','дом','спорт','книги','красота','игрушки','авто'])[1 + floor(random()*8)::int],
       round((5 + random() * 495)::numeric, 2)
FROM generate_series(1, 50000) g;

\echo 'orders (1.5M)...'
INSERT INTO orders
SELECT g,
       1 + floor(random() * 200000)::int,
       timestamp '2025-01-01' + (random() * 540) * interval '1 day',
       (ARRAY['paid','paid','paid','paid','paid','paid','paid','paid','paid','cancelled','refunded'])[1 + floor(random()*11)::int],
       round((10 + random() * 990)::numeric, 2)
FROM generate_series(1, 1500000) g;

\echo 'order_lines (4M)...'
INSERT INTO order_lines
SELECT g,
       1 + floor(random() * 1500000)::bigint,
       1 + floor(random() * 50000)::int,
       1 + floor(random() * 3)::int,
       round((5 + random() * 495)::numeric, 2)
FROM generate_series(1, 4000000) g;

\echo 'events (8M), порядок по времени...'
INSERT INTO events
SELECT g,
       1 + floor(random() * 200000)::int,
       timestamp '2025-01-01' + (g::numeric / 8000000 * 540) * interval '1 day'
                              + (random() * 6) * interval '1 hour',
       (ARRAY['page_view','page_view','page_view','page_view','search','add_to_cart','checkout_start','purchase'])[1 + floor(random()*8)::int],
       1 + floor(random() * 3000000)::bigint,
       (ARRAY['ios','android','web'])[1 + floor(random()*3)::int],
       (ARRAY['GE','AM','TR','DE','PL','RS'])[1 + floor(random()*6)::int],
       CASE WHEN random() < 0.06 THEN round((5 + random() * 495)::numeric, 2) END
FROM generate_series(1, 8000000) g;

\echo 'индексы (реалистичный стартовый набор, какой завела бы команда)...'
-- Намеренно НЕ индексируются: order_lines.order_id, order_lines.product_id,
-- events.user_id, events.event_name. Часть проекта — понять, каких индексов
-- не хватает, и доказать это планами.
CREATE INDEX ix_ev_ts      ON events(event_ts);
CREATE INDEX ix_ord_created ON orders(created_at);
CREATE INDEX ix_ord_user    ON orders(user_id);

\echo 'ANALYZE...'
ANALYZE users; ANALYZE products; ANALYZE orders; ANALYZE order_lines; ANALYZE events;

\echo 'Строк в таблицах:'
SELECT 'users' t, count(*) FROM users UNION ALL
SELECT 'products', count(*) FROM products UNION ALL
SELECT 'orders', count(*) FROM orders UNION ALL
SELECT 'order_lines', count(*) FROM order_lines UNION ALL
SELECT 'events', count(*) FROM events ORDER BY 1;

SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) size
FROM pg_catalog.pg_statio_user_tables WHERE schemaname='dwh' ORDER BY pg_total_relation_size(relid) DESC;
