-- Схема проекта спринта 6: сервис доставки еды «Скороход».
DROP SCHEMA IF EXISTS delivery CASCADE;
CREATE SCHEMA delivery;
SET search_path TO delivery, public;

CREATE TABLE cities (
    city_id     integer PRIMARY KEY,
    city        text NOT NULL,
    price_index numeric(4,2) NOT NULL   -- уровень цен относительно Тбилиси
);

CREATE TABLE restaurants (
    restaurant_id   integer PRIMARY KEY,
    restaurant_name text NOT NULL,
    city_id         integer NOT NULL REFERENCES cities(city_id),
    cuisine         text NOT NULL,
    rating          numeric(3,1) NOT NULL,
    commission_pct  numeric(4,1) NOT NULL,   -- комиссия сервиса, %
    joined_date     date NOT NULL
);
COMMENT ON COLUMN restaurants.commission_pct IS 'Доля заказа, которую забирает сервис. Основа выручки.';

CREATE TABLE couriers (
    courier_id      integer PRIMARY KEY,
    city_id         integer NOT NULL REFERENCES cities(city_id),
    vehicle         text NOT NULL,
    hired_date      date NOT NULL,
    terminated_date date          -- NULL — работает
);

CREATE TABLE customers (
    customer_id integer PRIMARY KEY,
    city_id     integer NOT NULL REFERENCES cities(city_id),
    signup_date date NOT NULL,
    platform    text NOT NULL
);

CREATE TABLE orders (
    order_id       integer PRIMARY KEY,
    customer_id    integer NOT NULL REFERENCES customers(customer_id),
    restaurant_id  integer NOT NULL REFERENCES restaurants(restaurant_id),
    courier_id     integer REFERENCES couriers(courier_id),
    created_at     timestamp NOT NULL,
    accepted_at    timestamp,
    picked_at      timestamp,
    delivered_at   timestamp,
    cancelled_at   timestamp,
    status         text NOT NULL,   -- delivered / cancelled_by_user / cancelled_by_restaurant / cancelled_by_courier
    items_total    numeric(10,2) NOT NULL,
    delivery_fee   numeric(8,2) NOT NULL,
    discount       numeric(10,2) NOT NULL,
    promo_code     text,
    payment_method text NOT NULL,
    rating         smallint         -- оценка заказа 1..5, NULL если не поставили
);
COMMENT ON TABLE orders IS
  'Заказы. Внимание: у части отменённых заполнено delivered_at, у части доставленных время доставки раньше создания.';
COMMENT ON COLUMN orders.items_total IS 'Сумма блюд без доставки и без скидки.';

CREATE TABLE order_items (
    order_id  integer NOT NULL REFERENCES orders(order_id),
    item_name text NOT NULL,
    qty       smallint NOT NULL,
    price     numeric(8,2) NOT NULL
);
COMMENT ON TABLE order_items IS 'Позиции заказа. Первичного ключа нет: одно блюдо может встретиться в заказе дважды.';

CREATE INDEX ix_ord_customer   ON orders(customer_id);
CREATE INDEX ix_ord_restaurant ON orders(restaurant_id);
CREATE INDEX ix_ord_courier    ON orders(courier_id);
CREATE INDEX ix_ord_created    ON orders(created_at);
CREATE INDEX ix_ord_status     ON orders(status);
CREATE INDEX ix_oi_order       ON order_items(order_id);
CREATE INDEX ix_rest_city      ON restaurants(city_id);
CREATE INDEX ix_cust_city      ON customers(city_id);
