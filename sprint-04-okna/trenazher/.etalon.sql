-- Эталонные решения тренажёра спринта 4.

-- TASK: t4.1
SELECT country, count(*) AS users,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS share_pct
FROM users GROUP BY country
ORDER BY users DESC, country NULLS LAST;

-- TASK: t4.2
SELECT count(*) AS uniq_rows FROM (
  SELECT row_number() OVER (PARTITION BY visitor_id, event_ts, event_name
                            ORDER BY page_event_id) AS rn
  FROM page_events WHERE event_name = 'landing_view'
) t WHERE rn = 1;

-- TASK: t4.3
SELECT g.game_name, count(*) AS bets,
       rank()       OVER (ORDER BY count(*) DESC) AS rnk,
       dense_rank() OVER (ORDER BY count(*) DESC) AS dense_rnk
FROM bets b JOIN games g ON g.game_id = b.game_id
GROUP BY g.game_name
ORDER BY bets DESC, g.game_name LIMIT 10;

-- TASK: t4.4
WITH ltv AS (
  SELECT user_id, sum(amount_eur) AS dep FROM deposits
  WHERE status = 'success' GROUP BY user_id
), d AS (
  SELECT dep, ntile(10) OVER (ORDER BY dep DESC) AS decile FROM ltv
)
SELECT round(100.0 * sum(dep) FILTER (WHERE decile = 1) / sum(dep), 1) AS top_decile_share_pct
FROM d;

-- TASK: t4.5
WITH t AS (
  SELECT g.category, g.game_name, sum(b.stake_eur) AS turnover,
         row_number() OVER (PARTITION BY g.category
                            ORDER BY sum(b.stake_eur) DESC, g.game_name) AS rn
  FROM bets b JOIN games g ON g.game_id = b.game_id
  GROUP BY g.category, g.game_name
)
SELECT category, game_name, round(turnover, 2) AS turnover, rn
FROM t WHERE rn <= 3 ORDER BY category, rn;

-- TASK: t4.6
WITH w AS (
  SELECT date_trunc('week', bet_ts)::date AS week_start, sum(stake_eur) AS turnover
  FROM bets GROUP BY 1
)
SELECT week_start, round(turnover, 2) AS turnover,
       round(100.0 * (turnover - lag(turnover) OVER (ORDER BY week_start))
             / lag(turnover) OVER (ORDER BY week_start), 1) AS wow_pct
FROM w ORDER BY week_start;

-- TASK: t4.7
WITH gaps AS (
  SELECT user_id,
         extract(epoch FROM (deposit_ts
                 - lag(deposit_ts) OVER (PARTITION BY user_id ORDER BY deposit_ts, deposit_id)))
         / 86400.0 AS days
  FROM deposits WHERE status = 'success'
)
SELECT round(avg(days)::numeric, 2) AS avg_days_between FROM gaps WHERE days IS NOT NULL;

-- TASK: t4.8
WITH d AS (
  SELECT deposit_ts::date AS d, sum(amount_eur) AS daily
  FROM deposits WHERE status = 'success' GROUP BY 1
)
SELECT d, round(daily, 2) AS daily,
       round(sum(daily) OVER (ORDER BY d ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS cumulative
FROM d ORDER BY d;

-- TASK: t4.9
WITH d AS (
  SELECT bet_ts::date AS d, sum(stake_eur) AS turnover FROM bets GROUP BY 1
)
SELECT d, round(turnover, 2) AS turnover,
       round(avg(turnover) OVER (ORDER BY d ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS ma7
FROM d ORDER BY d;

-- TASK: t4.10
WITH fl AS (
  SELECT DISTINCT user_id,
         first_value(game_id) OVER (PARTITION BY user_id ORDER BY bet_ts, bet_id
                                    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS first_game,
         last_value(game_id)  OVER (PARTITION BY user_id ORDER BY bet_ts, bet_id
                                    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS last_game
  FROM bets
)
SELECT round(100.0 * count(*) FILTER (WHERE first_game = last_game) / count(*), 1) AS same_game_pct
FROM fl;

-- TASK: t4.11
WITH c AS (
  SELECT user_id, deposit_ts,
         sum(amount_eur) OVER (PARTITION BY user_id ORDER BY deposit_ts, deposit_id
                               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running
  FROM deposits WHERE status = 'success'
)
SELECT count(*) AS deposits_over_500 FROM c WHERE running > 500;

-- TASK: t4.12
SELECT round(percentile_cont(0.25) WITHIN GROUP (ORDER BY amount_eur)::numeric, 2) AS p25,
       round(percentile_cont(0.50) WITHIN GROUP (ORDER BY amount_eur)::numeric, 2) AS p50,
       round(percentile_cont(0.75) WITHIN GROUP (ORDER BY amount_eur)::numeric, 2) AS p75,
       round(percentile_cont(0.90) WITHIN GROUP (ORDER BY amount_eur)::numeric, 2) AS p90
FROM deposits WHERE status = 'success';

-- TASK: t4.13
WITH ftd AS (
  SELECT u.source, d.amount_eur
  FROM deposits d JOIN users u ON u.user_id = d.user_id
  WHERE d.status = 'success' AND d.dep_number = 1
)
SELECT source, round(avg(amount_eur), 2) AS avg_ftd,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY amount_eur)::numeric, 2) AS median_ftd
FROM ftd GROUP BY source
ORDER BY avg_ftd DESC, source NULLS LAST;

-- TASK: t4.14
SELECT g.category,
       round(avg(b.stake_eur), 3) AS avg_stake,
       round(stddev_samp(b.stake_eur), 3) AS stddev_stake,
       round((percentile_cont(0.75) WITHIN GROUP (ORDER BY b.stake_eur)
            - percentile_cont(0.25) WITHIN GROUP (ORDER BY b.stake_eur))::numeric, 3) AS iqr
FROM bets b JOIN games g ON g.game_id = b.game_id
GROUP BY g.category ORDER BY g.category;

-- TASK: t4.15
SELECT mode() WITHIN GROUP (ORDER BY method) AS top_method
FROM deposits WHERE status = 'success';

-- TASK: t4.16
SELECT count(*) AS users FROM (
  SELECT user_id, max(amount_eur) AS mx FROM deposits
  WHERE status = 'success' GROUP BY user_id
) t WHERE mx > 300;

-- TASK: t4.17
WITH ftd AS (
  SELECT u.user_id,
         extract(epoch FROM (min(d.deposit_ts) - u.reg_ts)) / 3600.0 AS hours
  FROM users u
  LEFT JOIN deposits d ON d.user_id = u.user_id AND d.status = 'success'
  GROUP BY u.user_id, u.reg_ts
)
SELECT CASE
         WHEN hours IS NULL THEN '5. не платил'
         WHEN hours < 1 THEN '1. до часа'
         WHEN hours < 24 THEN '2. в первые сутки'
         WHEN hours < 168 THEN '3. в первую неделю'
         ELSE '4. позже'
       END AS bucket,
       count(*) AS users
FROM ftd GROUP BY bucket ORDER BY bucket;

-- TASK: t4.18
WITH v AS (
  SELECT date_trunc('week', first_seen_ts)::date AS week_start, visitor_id
  FROM visitors
), s AS (
  SELECT DISTINCT visitor_id FROM page_events WHERE event_name = 'signup_start'
)
SELECT v.week_start, count(*) AS visits,
       count(s.visitor_id) AS starts,
       round(100.0 * count(s.visitor_id) / count(*), 2) AS cr_pct
FROM v LEFT JOIN s ON s.visitor_id = v.visitor_id
GROUP BY v.week_start ORDER BY v.week_start;

-- TASK: t4.19
WITH d AS (
  SELECT DISTINCT user_id, session_date FROM sessions
), grp AS (
  SELECT user_id, session_date,
         session_date - (row_number() OVER (PARTITION BY user_id ORDER BY session_date))::int AS island
  FROM d
), streaks AS (
  SELECT user_id, island, count(*) AS len FROM grp GROUP BY user_id, island
)
SELECT max(len) AS max_streak FROM streaks;

-- TASK: t4.20
WITH t AS (
  SELECT user_id, sum(stake_eur) AS turnover,
         percent_rank() OVER (ORDER BY sum(stake_eur) DESC) AS pr
  FROM bets GROUP BY user_id
)
SELECT count(*) FILTER (WHERE pr < 0.10) AS players,
       round(100.0 * sum(turnover) FILTER (WHERE pr < 0.10) / sum(turnover), 1) AS share_pct
FROM t;
