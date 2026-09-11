-- Сбор признаков для проекта спринта 20.
--
-- ВНИМАНИЕ: этот запрос собирает и честные признаки, и заведомо
-- протекающие. Так сделано намеренно: часть проекта — понять, какие
-- из них нельзя использовать, и доказать это.
--
-- Выгрузка:
--   docker compose exec -T postgres psql -U analyst -d casino -q \
--     -f /course/sprint-20-ml/project/sql/features.sql > features.csv

SET search_path TO casino, public;

COPY (
WITH ftd AS (
    SELECT user_id, min(deposit_ts) AS first_deposit_ts
    FROM deposits WHERE status = 'success' GROUP BY 1
),
u AS (
    SELECT u.user_id, u.reg_ts, u.reg_date, u.country, u.source, u.device,
           u.birth_year, u.is_verified, u.vip_level,
           (f.user_id IS NOT NULL)::int AS y
    FROM users u LEFT JOIN ftd f USING (user_id)
),
-- окно первых суток после регистрации: то, что известно на момент прогноза
s24 AS (
    SELECT u.user_id,
           count(s.session_id) AS sess_24h,
           coalesce(sum(s.duration_sec), 0) AS sec_24h
    FROM u LEFT JOIN sessions s
      ON s.user_id = u.user_id
     AND s.started_at >= u.reg_ts
     AND s.started_at <  u.reg_ts + interval '24 hours'
    GROUP BY 1
),
-- поведение ДО регистрации: канал и активность на сайте
v AS (
    SELECT user_id, min(utm_source) AS utm_source, count(*) AS visits
    FROM visitors WHERE user_id IS NOT NULL GROUP BY 1
),
pe AS (
    SELECT vi.user_id, count(*) AS page_events_pre
    FROM page_events p
    JOIN visitors vi USING (visitor_id)
    JOIN u ON u.user_id = vi.user_id
    WHERE vi.user_id IS NOT NULL AND p.event_ts < u.reg_ts
    GROUP BY 1
),
-- ВСЕ сессии за всю историю: 83% из них происходят ПОСЛЕ первого депозита
sa AS (
    SELECT user_id, count(*) AS sess_total FROM sessions GROUP BY 1
)
SELECT u.user_id,
       u.reg_date,
       u.country,
       u.source,
       u.device,
       u.birth_year,
       u.is_verified,                              -- поле-состояние без времени
       u.vip_level,                                -- поле-состояние без времени
       s24.sess_24h,
       s24.sec_24h,
       coalesce(v.utm_source, 'none') AS utm_source,
       coalesce(v.visits, 0)          AS visits,
       coalesce(pe.page_events_pre, 0) AS page_events_pre,
       coalesce(sa.sess_total, 0)      AS sess_total,   -- считается за всю историю
       u.y
FROM u
LEFT JOIN s24 USING (user_id)
LEFT JOIN v   USING (user_id)
LEFT JOIN pe  USING (user_id)
LEFT JOIN sa  USING (user_id)
ORDER BY u.reg_ts
) TO STDOUT WITH CSV HEADER;
