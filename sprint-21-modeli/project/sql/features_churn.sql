-- Признаки для модели оттока. Проект спринта 21.
--
-- Отсечка: 30 апреля 2026. Всё, что левее, — признаки.
-- Окно наблюдения: 30 апреля — 29 июня (60 дней). Отток = ни одного
-- доставленного заказа в этом окне.
--
-- В выборку берутся клиенты, сделавшие хотя бы один доставленный заказ
-- ДО отсечки: у остальных предсказывать нечего.
--
-- Выгрузка:
--   docker compose exec -T postgres psql -U analyst -d casino -q \
--     -f /course/sprint-21-modeli/project/sql/features_churn.sql > churn.csv

SET search_path TO delivery, public;

COPY (
WITH obs AS (SELECT DATE '2026-04-30' AS cut),
hist AS (
    SELECT o.customer_id,
           count(*)                                   AS orders_total,
           count(*) FILTER (WHERE o.created_at >= obs.cut - 30) AS orders_30d,
           count(*) FILTER (WHERE o.created_at >= obs.cut - 90) AS orders_90d,
           max(o.created_at)::date                    AS last_order,
           min(o.created_at)::date                    AS first_order,
           round(avg(o.items_total), 2)               AS avg_check,
           round(sum(o.items_total), 2)               AS monetary,
           round(avg(o.rating), 2)                    AS avg_rating,
           count(*) FILTER (WHERE o.promo_code IS NOT NULL) AS promo_orders
    FROM orders o, obs
    WHERE o.status = 'delivered' AND o.created_at < obs.cut
    GROUP BY 1
),
cancels AS (
    SELECT o.customer_id, count(*) AS cancelled
    FROM orders o, obs
    WHERE o.status <> 'delivered' AND o.created_at < obs.cut
    GROUP BY 1
),
future AS (
    SELECT DISTINCT o.customer_id
    FROM orders o, obs
    WHERE o.status = 'delivered' AND o.created_at >= obs.cut
)
SELECT h.customer_id,
       ci.city,
       c.platform,
       h.orders_total,
       h.orders_30d,
       h.orders_90d,
       (obs.cut - h.last_order)   AS recency_days,
       (obs.cut - h.first_order)  AS tenure_days,
       h.avg_check,
       h.monetary,
       coalesce(h.avg_rating, -1) AS avg_rating,      -- -1 = оценок не ставил
       h.promo_orders,
       coalesce(x.cancelled, 0)   AS cancelled,
       (f.customer_id IS NULL)::int AS churned
FROM hist h
JOIN customers c ON c.customer_id = h.customer_id
JOIN cities ci   ON ci.city_id = c.city_id
LEFT JOIN cancels x ON x.customer_id = h.customer_id
LEFT JOIN future  f ON f.customer_id = h.customer_id
CROSS JOIN obs
ORDER BY h.customer_id
) TO STDOUT WITH CSV HEADER;
