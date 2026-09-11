-- Эталонные решения тренажёра спринта 3.

-- TASK: t3.1
SELECT g.game_name, g.provider, round(sum(b.stake_eur), 2) AS turnover
FROM bets b JOIN games g ON g.game_id = b.game_id
GROUP BY g.game_name, g.provider
ORDER BY turnover DESC, g.game_name LIMIT 10;

-- TASK: t3.2
SELECT count(*) AS users_without_bets
FROM users u LEFT JOIN bets b ON b.user_id = u.user_id
WHERE b.user_id IS NULL;

-- TASK: t3.3
SELECT u.country, count(DISTINCT u.user_id) AS users,
       count(d.deposit_id) AS success_deposits
FROM users u
LEFT JOIN deposits d ON d.user_id = u.user_id AND d.status = 'success'
GROUP BY u.country
ORDER BY users DESC, u.country NULLS LAST;

-- TASK: t3.4
WITH dep AS (
  SELECT user_id, sum(amount_eur) AS dep_sum FROM deposits
  WHERE status = 'success' GROUP BY user_id
), ses AS (
  SELECT user_id, count(*) AS sessions FROM sessions GROUP BY user_id
)
SELECT u.source,
       round(coalesce(sum(dep.dep_sum), 0), 2) AS dep_sum,
       coalesce(sum(ses.sessions), 0) AS sessions
FROM users u
LEFT JOIN dep ON dep.user_id = u.user_id
LEFT JOIN ses ON ses.user_id = u.user_id
GROUP BY u.source
ORDER BY dep_sum DESC, u.source NULLS LAST;

-- TASK: t3.5
SELECT count(*) AS users
FROM (SELECT DISTINCT user_id FROM events WHERE event_name = 'wallet_open') w
WHERE NOT EXISTS (
  SELECT 1 FROM events e
  WHERE e.user_id = w.user_id AND e.event_name = 'deposit_start');

-- TASK: t3.6
SELECT 'in' AS direction, count(*) AS cnt, round(sum(amount_eur), 2) AS total_eur
FROM deposits WHERE status = 'success'
UNION ALL
SELECT 'out', count(*), round(sum(amount_eur), 2)
FROM withdrawals WHERE status = 'paid'
ORDER BY direction;

-- TASK: t3.7
WITH bettors AS (SELECT DISTINCT user_id FROM bets),
     payers  AS (SELECT DISTINCT user_id FROM deposits WHERE status = 'success')
SELECT 'and_bet_and_paid' AS segment,
       count(*) AS users FROM (SELECT * FROM bettors INTERSECT SELECT * FROM payers) x
UNION ALL
SELECT 'bet_not_paid', count(*) FROM (SELECT * FROM bettors EXCEPT SELECT * FROM payers) x
UNION ALL
SELECT 'paid_not_bet', count(*) FROM (SELECT * FROM payers EXCEPT SELECT * FROM bettors) x
ORDER BY segment;

-- TASK: t3.8
SELECT g.category,
       round(sum(b.stake_eur), 2) AS turnover,
       round(100.0 * sum(b.stake_eur) / (SELECT sum(stake_eur) FROM bets), 1) AS share_pct
FROM bets b JOIN games g ON g.game_id = b.game_id
GROUP BY g.category ORDER BY turnover DESC;

-- TASK: t3.9
SELECT count(*) AS users FROM users u
WHERE EXISTS (SELECT 1 FROM support_tickets t
              WHERE t.user_id = u.user_id AND t.category = 'payment');

-- TASK: t3.10
WITH first_bet AS (
  SELECT DISTINCT ON (user_id) user_id, game_id
  FROM bets ORDER BY user_id, bet_ts, bet_id
)
SELECT g.game_name, count(*) AS first_bets
FROM first_bet f JOIN games g ON g.game_id = f.game_id
GROUP BY g.game_name
ORDER BY first_bets DESC, g.game_name LIMIT 5;

-- TASK: t3.11
WITH ftd AS (
  SELECT DISTINCT ON (user_id) user_id, amount_eur
  FROM deposits WHERE status = 'success' AND dep_number = 1
  ORDER BY user_id, deposit_ts, deposit_id
)
SELECT u.source, count(*) AS regs, count(f.user_id) AS ftd,
       round(avg(f.amount_eur), 2) AS avg_ftd
FROM users u LEFT JOIN ftd f ON f.user_id = u.user_id
GROUP BY u.source
ORDER BY regs DESC, u.source NULLS LAST;

-- TASK: t3.12
WITH ftd AS (
  SELECT user_id, amount_eur FROM deposits
  WHERE status = 'success' AND dep_number = 1
)
SELECT CASE
         WHEN amount_eur < 20 THEN '1. до 20'
         WHEN amount_eur < 50 THEN '2. 20-50'
         WHEN amount_eur < 100 THEN '3. 50-100'
         WHEN amount_eur < 250 THEN '4. 100-250'
         ELSE '5. 250+'
       END AS bucket,
       count(*) AS users
FROM ftd GROUP BY bucket ORDER BY bucket;

-- TASK: t3.13
SELECT date_trunc('week', bet_ts)::date AS week_start,
       round(sum(stake_eur), 2) AS turnover
FROM bets GROUP BY 1 ORDER BY 1;

-- TASK: t3.14
SELECT extract(hour FROM bet_ts)::int AS hour, count(*) AS bets
FROM bets GROUP BY 1 ORDER BY 1;

-- TASK: t3.15
WITH ftd AS (
  SELECT d.user_id, min(d.deposit_ts) AS ftd_ts
  FROM deposits d WHERE d.status = 'success' GROUP BY d.user_id
)
SELECT round(percentile_cont(0.5) WITHIN GROUP (
         ORDER BY extract(epoch FROM (f.ftd_ts - u.reg_ts)) / 3600.0)::numeric, 1) AS median_hours
FROM ftd f JOIN users u ON u.user_id = f.user_id;

-- TASK: t3.16
SELECT d::date AS d, count(dp.deposit_id) AS deposits
FROM generate_series('2026-03-01'::date, '2026-03-31'::date, '1 day') AS d
LEFT JOIN deposits dp ON dp.deposit_ts::date = d::date AND dp.status = 'success'
GROUP BY d ORDER BY d;

-- TASK: t3.17
WITH RECURSIVE chain AS (
  SELECT attempt_id, 1 AS len FROM payment_attempts WHERE retry_of IS NULL
  UNION ALL
  SELECT p.attempt_id, c.len + 1
  FROM payment_attempts p JOIN chain c ON p.retry_of = c.attempt_id
)
SELECT max(len) AS max_chain_len FROM chain;

-- TASK: t3.18
WITH last_s AS (
  SELECT DISTINCT ON (user_id) user_id, session_date
  FROM sessions ORDER BY user_id, session_date DESC
)
SELECT l.user_id, l.session_date AS last_session
FROM last_s l
WHERE EXISTS (SELECT 1 FROM deposits d
              WHERE d.user_id = l.user_id AND d.status = 'success')
ORDER BY l.session_date, l.user_id LIMIT 5;
