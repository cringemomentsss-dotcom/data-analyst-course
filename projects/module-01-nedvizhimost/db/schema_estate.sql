-- Схема итогового проекта модуля 1: объявления о продаже жилья.
DROP SCHEMA IF EXISTS estate CASCADE;
CREATE SCHEMA estate;
SET search_path TO estate, public;

CREATE TABLE localities (
    locality_id   integer PRIMARY KEY,
    locality_name text NOT NULL,
    locality_type text NOT NULL,
    population    integer NOT NULL
);
COMMENT ON TABLE localities IS 'Справочник населённых пунктов. Тип записан непоследовательно.';

CREATE TABLE listings (
    listing_id       integer PRIMARY KEY,
    posted_date      date NOT NULL,
    removed_date     date,           -- NULL — объявление ещё активно
    days_exposition  integer,        -- NULL — ещё активно
    locality_id      integer NOT NULL REFERENCES localities(locality_id),
    price_rub        numeric(14,2) NOT NULL,
    rooms            smallint NOT NULL,   -- 0 — студия
    area_total       numeric(7,1) NOT NULL,
    area_living      numeric(7,1),
    area_kitchen     numeric(7,1),
    ceiling_height   numeric(5,2),
    floor            smallint NOT NULL,
    floors_total     smallint NOT NULL,
    is_apartment     smallint NOT NULL,
    is_studio        smallint NOT NULL,
    is_open_plan     smallint NOT NULL,
    balconies        smallint,
    airport_dist_m   integer,
    center_dist_m    integer,
    parks_around_3000 smallint,
    park_nearest_m   integer,
    ponds_around_3000 smallint,
    pond_nearest_m   integer,
    images_count     smallint
);
COMMENT ON TABLE listings IS
  'Объявления о продаже. Выгрузка из классифайда: пропуски, выбросы и дубликаты присутствуют.';
COMMENT ON COLUMN listings.days_exposition IS 'Сколько дней объявление провисело до снятия.';
COMMENT ON COLUMN listings.removed_date IS 'NULL — объявление активно на конец периода.';

CREATE INDEX ix_lst_locality ON listings(locality_id);
CREATE INDEX ix_lst_posted   ON listings(posted_date);
