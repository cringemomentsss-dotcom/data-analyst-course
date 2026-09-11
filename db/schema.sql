-- ============================================================================
--  Учебная база курса «Аналитик данных» — PostgreSQL 17
--
--  Домен: онлайн-казино. Семь таблиц перенесены один в один из casino.db
--  (курс SQL, август 2026) — схема та же, данные те же. Восемь таблиц
--  добавлены: трафик, воронка визитов, эксперименты, платёжные попытки,
--  бонусы, саппорт, маркетинговые расходы.
--
--  Данные синтетические и детерминированные. Реальных людей здесь нет.
-- ============================================================================

DROP SCHEMA IF EXISTS casino CASCADE;
CREATE SCHEMA casino;
SET search_path TO casino, public;

-- ---------------------------------------------------------------------------
-- ЧАСТЬ 1. Ядро — то же, что в курсе SQL
-- ---------------------------------------------------------------------------

CREATE TABLE users (
    user_id     integer PRIMARY KEY,
    reg_ts      timestamp   NOT NULL,
    reg_date    date        NOT NULL,
    country     text,                    -- 103 NULL: страну не определили по IP
    source      text,                    -- 22 NULL: метка канала потерялась
    device      text        NOT NULL,
    birth_year  integer,
    is_verified smallint    NOT NULL,
    vip_level   smallint    NOT NULL
);
COMMENT ON TABLE  users IS 'Зарегистрированные игроки. Одна строка — один игрок.';
COMMENT ON COLUMN users.source IS 'Канал привлечения на момент регистрации. NULL — метка не проставилась.';
COMMENT ON COLUMN users.vip_level IS '0 — обычный, 3 — максимальный.';

CREATE TABLE games (
    game_id   integer PRIMARY KEY,
    game_name text    NOT NULL,
    provider  text    NOT NULL,
    category  text    NOT NULL,          -- slots / live / table / crash
    rtp       numeric(5,2) NOT NULL      -- return to player, %
);
COMMENT ON TABLE games IS 'Справочник игр. Одна строка — одна игра.';

CREATE TABLE events (
    event_id   integer PRIMARY KEY,
    user_id    integer NOT NULL REFERENCES users(user_id),
    event_ts   timestamp NOT NULL,
    event_name text    NOT NULL,         -- registration / wallet_open / deposit_start / deposit_success
    platform   text
);
COMMENT ON TABLE events IS 'Продуктовые события зарегистрированных игроков. Разметка неполная — см. page_events.';

CREATE TABLE sessions (
    session_id   integer PRIMARY KEY,
    user_id      integer NOT NULL REFERENCES users(user_id),
    started_at   timestamp NOT NULL,
    session_date date    NOT NULL,
    duration_sec integer NOT NULL,
    device       text    NOT NULL
);
COMMENT ON TABLE sessions IS 'Игровые сессии. Одна строка — один вход в продукт.';

CREATE TABLE deposits (
    deposit_id integer PRIMARY KEY,
    user_id    integer NOT NULL REFERENCES users(user_id),
    deposit_ts timestamp NOT NULL,
    amount_eur numeric(12,2) NOT NULL,
    method     text    NOT NULL,
    status     text    NOT NULL,         -- success / failed
    dep_number integer                   -- порядковый номер УСПЕШНОГО депозита; NULL у неуспешных
);
COMMENT ON TABLE deposits IS 'Транзакции пополнения по данным платёжного провайдера.';
COMMENT ON COLUMN deposits.dep_number IS 'dep_number = 1 → первый депозит игрока (FTD).';

CREATE TABLE withdrawals (
    withdrawal_id integer PRIMARY KEY,
    user_id       integer NOT NULL REFERENCES users(user_id),
    withdrawal_ts timestamp NOT NULL,
    amount_eur    numeric(12,2) NOT NULL,
    status        text    NOT NULL
);
COMMENT ON TABLE withdrawals IS 'Заявки на вывод средств.';

CREATE TABLE bets (
    bet_id     integer PRIMARY KEY,
    user_id    integer NOT NULL REFERENCES users(user_id),
    bet_ts     timestamp NOT NULL,
    game_id    integer NOT NULL REFERENCES games(game_id),
    stake_eur  numeric(12,2) NOT NULL,
    payout_eur numeric(12,2) NOT NULL
);
COMMENT ON TABLE bets IS 'Ставки. GGR = SUM(stake_eur) - SUM(payout_eur).';

-- ---------------------------------------------------------------------------
-- ЧАСТЬ 2. Трафик и воронка визитов
-- ---------------------------------------------------------------------------

CREATE TABLE visitors (
    visitor_id    bigint PRIMARY KEY,
    first_seen_ts timestamp NOT NULL,
    country       text,
    device        text NOT NULL,
    utm_source    text,
    utm_medium    text,
    utm_campaign  text,
    landing_page  text NOT NULL,
    user_id       integer REFERENCES users(user_id)   -- NOT NULL только у зарегистрировавшихся
);
COMMENT ON TABLE visitors IS 'Посетители сайта. Единица A/B-экспериментов на верхней воронке. ~0.4% доходят до регистрации.';
COMMENT ON COLUMN visitors.user_id IS 'Связь визита с игроком. NULL — визит не привёл к регистрации.';

CREATE TABLE page_events (
    page_event_id bigint PRIMARY KEY,
    visitor_id    bigint NOT NULL REFERENCES visitors(visitor_id),
    event_ts      timestamp NOT NULL,
    event_name    text NOT NULL,   -- landing_view / promo_view / game_demo / signup_start / signup_complete
    page          text,
    device        text
);
COMMENT ON TABLE page_events IS 'Веб-аналитика верхней воронки. Внимание: часть событий задваивается — трекер срабатывает дважды.';

-- ---------------------------------------------------------------------------
-- ЧАСТЬ 3. Эксперименты
-- ---------------------------------------------------------------------------

CREATE TABLE experiments (
    experiment_id  text PRIMARY KEY,
    name           text NOT NULL,
    hypothesis     text NOT NULL,
    unit           text NOT NULL,        -- visitor / user
    primary_metric text NOT NULL,
    start_date     date NOT NULL,
    end_date       date NOT NULL,
    planned_split  text NOT NULL,        -- '50/50'
    status         text NOT NULL
);
COMMENT ON TABLE experiments IS 'Паспорта A/B-экспериментов. Заполняются до запуска.';

CREATE TABLE ab_assignments (
    experiment_id text   NOT NULL REFERENCES experiments(experiment_id),
    unit_id       bigint NOT NULL,       -- visitor_id или user_id, смотря что в experiments.unit
    variant       text   NOT NULL,       -- control / treatment
    assigned_ts   timestamp NOT NULL,
    PRIMARY KEY (experiment_id, unit_id)
);
COMMENT ON TABLE ab_assignments IS 'Назначение вариантов. Проверь фактическое соотношение групп перед анализом.';

-- ---------------------------------------------------------------------------
-- ЧАСТЬ 4. Платежи, бонусы, поддержка, расходы
-- ---------------------------------------------------------------------------

CREATE TABLE payment_attempts (
    attempt_id     bigint PRIMARY KEY,
    user_id        integer NOT NULL REFERENCES users(user_id),
    attempt_ts     timestamp NOT NULL,
    amount_eur     numeric(12,2) NOT NULL,
    method         text NOT NULL,
    provider       text NOT NULL,
    status         text NOT NULL,        -- success / declined / timeout / abandoned
    decline_reason text,
    retry_of       bigint REFERENCES payment_attempts(attempt_id)
);
COMMENT ON TABLE payment_attempts IS 'Лог фронтенда: все попытки оплаты, включая не дошедшие до провайдера. Шире, чем deposits.';
COMMENT ON COLUMN payment_attempts.retry_of IS 'Ссылка на предыдущую неудачную попытку той же цепочки.';

CREATE TABLE bonuses (
    bonus_id        integer PRIMARY KEY,
    user_id         integer NOT NULL REFERENCES users(user_id),
    granted_ts      timestamp NOT NULL,
    bonus_type      text NOT NULL,       -- welcome / reload / cashback / freespins
    amount_eur      numeric(12,2) NOT NULL,
    wager_multiplier smallint NOT NULL,
    status          text NOT NULL,       -- active / completed / expired / cancelled
    completed_ts    timestamp
);
COMMENT ON TABLE bonuses IS 'Выданные бонусы и их отыгрыш.';

CREATE TABLE support_tickets (
    ticket_id   integer PRIMARY KEY,
    user_id     integer NOT NULL REFERENCES users(user_id),
    created_ts  timestamp NOT NULL,
    resolved_ts timestamp,
    category    text NOT NULL,           -- payment / bonus / account / game / kyc
    channel     text NOT NULL,           -- chat / email
    csat        smallint                 -- 1..5, NULL если оценку не поставили
);
COMMENT ON TABLE support_tickets IS 'Обращения в поддержку. В нескольких строках resolved_ts раньше created_ts — это баг выгрузки, а не данные.';

CREATE TABLE marketing_spend (
    spend_date  date NOT NULL,
    channel     text NOT NULL,
    campaign    text NOT NULL,
    cost_eur    numeric(12,2) NOT NULL,
    impressions integer NOT NULL,
    clicks      integer NOT NULL,
    PRIMARY KEY (spend_date, channel, campaign)
);
COMMENT ON TABLE marketing_spend IS 'Расходы на привлечение по дням. Основа для CAC и юнит-экономики. Есть пропущенные дни.';

-- ---------------------------------------------------------------------------
-- Индексы
-- ---------------------------------------------------------------------------

CREATE INDEX ix_events_user      ON events(user_id);
CREATE INDEX ix_events_name      ON events(event_name);
CREATE INDEX ix_events_ts        ON events(event_ts);
CREATE INDEX ix_sessions_user    ON sessions(user_id);
CREATE INDEX ix_sessions_date    ON sessions(session_date);
CREATE INDEX ix_deposits_user    ON deposits(user_id);
CREATE INDEX ix_deposits_ts      ON deposits(deposit_ts);
CREATE INDEX ix_bets_user        ON bets(user_id);
CREATE INDEX ix_bets_game        ON bets(game_id);
CREATE INDEX ix_bets_ts          ON bets(bet_ts);
CREATE INDEX ix_visitors_seen    ON visitors(first_seen_ts);
CREATE INDEX ix_visitors_user    ON visitors(user_id);
CREATE INDEX ix_pe_visitor       ON page_events(visitor_id);
CREATE INDEX ix_pe_name_ts       ON page_events(event_name, event_ts);
CREATE INDEX ix_ab_unit          ON ab_assignments(unit_id);
CREATE INDEX ix_pa_user          ON payment_attempts(user_id);
CREATE INDEX ix_bonuses_user     ON bonuses(user_id);
CREATE INDEX ix_tickets_user     ON support_tickets(user_id);
