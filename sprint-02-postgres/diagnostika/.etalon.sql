-- Эталонные решения диагностики. Не подглядывать до сдачи.

-- TASK: d1
SELECT count(*) AS regs FROM users WHERE reg_date BETWEEN '2026-03-01' AND '2026-03-31';

-- TASK: d2
SELECT country, count(*) AS users FROM users
WHERE country IS NOT NULL GROUP BY country
ORDER BY users DESC, country LIMIT 5;

-- TASK: d3
SELECT method, count(*) AS deposits, round(avg(amount_eur), 2) AS avg_amount
FROM deposits WHERE status = 'success'
GROUP BY method HAVING count(*) >= 50
ORDER BY deposits DESC, method;

-- TASK: d4
SELECT count(*) AS users_without_deposit FROM users u
LEFT JOIN deposits d ON d.user_id = u.user_id
WHERE d.user_id IS NULL;

-- TASK: d5
SELECT u.source, count(*) AS regs,
       count(f.user_id) AS ftd,
       round(100.0 * count(f.user_id) / count(*), 1) AS cr_pct
FROM users u
LEFT JOIN (SELECT DISTINCT user_id FROM deposits WHERE status='success' AND dep_number=1) f
       ON f.user_id = u.user_id
GROUP BY u.source
ORDER BY regs DESC, u.source NULLS LAST;

-- TASK: d6
SELECT g.category,
       round(sum(b.stake_eur), 2) AS turnover,
       round(sum(b.stake_eur - b.payout_eur), 2) AS ggr,
       round(100.0 * sum(b.stake_eur - b.payout_eur) / sum(b.stake_eur), 2) AS margin_pct
FROM bets b JOIN games g ON g.game_id = b.game_id
GROUP BY g.category ORDER BY turnover DESC;

-- TASK: d7
SELECT user_id, count(*) AS sessions,
       row_number() OVER (ORDER BY count(*) DESC, user_id) AS rnk
FROM sessions GROUP BY user_id
ORDER BY sessions DESC, user_id LIMIT 5;

-- TASK: d8
WITH m AS (
  SELECT date_trunc('month', bet_ts)::date AS mon, sum(stake_eur) AS turnover
  FROM bets GROUP BY 1
)
SELECT mon, round(turnover, 2) AS turnover,
       round(100.0 * (turnover - lag(turnover) OVER (ORDER BY mon))
             / lag(turnover) OVER (ORDER BY mon), 1) AS mom_pct
FROM m ORDER BY mon;

-- TASK: d9
WITH ftd AS (
  SELECT d.user_id, min(d.deposit_ts) AS ftd_ts
  FROM deposits d WHERE d.status='success' GROUP BY d.user_id
)
SELECT round(100.0 * count(*) FILTER (WHERE ftd_ts::date = u.reg_date) / count(*), 1) AS same_day_pct
FROM ftd JOIN users u ON u.user_id = ftd.user_id;

-- TASK: d10
WITH d1 AS (
  SELECT DISTINCT s.user_id FROM sessions s JOIN users u ON u.user_id = s.user_id
  WHERE s.session_date = u.reg_date + 1
)
SELECT date_trunc('month', u.reg_date)::date AS reg_month,
       count(*) AS users,
       round(100.0 * count(d1.user_id) / count(*), 1) AS d1_pct
FROM users u LEFT JOIN d1 ON d1.user_id = u.user_id
GROUP BY 1 ORDER BY 1;

-- TASK: d11
WITH steps AS (
  SELECT 1 AS ord, 'registration' AS step, count(DISTINCT user_id) AS users FROM events WHERE event_name='registration'
  UNION ALL SELECT 2, 'wallet_open', count(DISTINCT user_id) FROM events WHERE event_name='wallet_open'
  UNION ALL SELECT 3, 'deposit_start', count(DISTINCT user_id) FROM events WHERE event_name='deposit_start'
  UNION ALL SELECT 4, 'deposit_success', count(DISTINCT user_id) FROM events WHERE event_name='deposit_success'
)
SELECT step, users,
       round(100.0 * users / lag(users) OVER (ORDER BY ord), 1) AS step_cr_pct
FROM steps ORDER BY ord;

-- TASK: d12
SELECT count(*) AS rows_total,
       count(DISTINCT visitor_id) AS uniq_visitors,
       count(*) - count(DISTINCT visitor_id) AS dup_rows
FROM page_events WHERE event_name = 'landing_view';
