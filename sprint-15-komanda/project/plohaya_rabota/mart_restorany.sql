-- Витрина по ресторанам и кухням для дашборда
-- автор: Костя (стажёр), октябрь
-- задача из джиры: DA-417 "нужна аналитика по кухням, решаем кого продвигать"

SELECT *
FROM orders o
JOIN restaurants r ON r.restaurant_id = o.restaurant_id
JOIN order_items oi ON oi.order_id = o.order_id
JOIN cities c ON c.city_id = r.city_id
WHERE o.created_at BETWEEN '2025-10-01' AND '2026-06-29'
  AND o.promo_code <> 'NONE'
;


-- итоговая агрегация для дашборда: выручка сервиса по кухням
SELECT
    r.cuisine,
    count(*) AS orders,
    sum(o.items_total * r.commission_pct / 100) AS revenue,
    avg(o.items_total) AS avg_check,
    avg(o.rating) AS avg_rating
FROM orders o
JOIN restaurants r ON r.restaurant_id = o.restaurant_id
JOIN order_items oi ON oi.order_id = o.order_id
WHERE o.created_at BETWEEN '2025-10-01' AND '2026-06-29'
  AND o.promo_code <> 'NONE'
GROUP BY r.cuisine
ORDER BY revenue DESC
;


-- время доставки по городам
SELECT
    c.city,
    avg(EXTRACT(epoch FROM (o.delivered_at - o.created_at)) / 60) AS avg_delivery_min,
    count(*) AS n
FROM orders o
JOIN restaurants r ON r.restaurant_id = o.restaurant_id
JOIN cities c ON c.city_id = r.city_id
WHERE o.delivered_at IS NOT NULL
GROUP BY c.city
ORDER BY avg_delivery_min DESC
;


-- топ ресторанов для продвижения
SELECT
    r.restaurant_name,
    r.cuisine,
    sum(o.items_total * r.commission_pct / 100) AS revenue,
    r.rating
FROM orders o
JOIN restaurants r ON r.restaurant_id = o.restaurant_id
WHERE o.created_at BETWEEN '2025-10-01' AND '2026-06-29'
  AND r.rating > 4.2
GROUP BY r.restaurant_name, r.cuisine, r.rating
ORDER BY revenue DESC
LIMIT 20
;
