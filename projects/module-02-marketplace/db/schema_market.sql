-- Схема итогового проекта модуля 2: маркетплейс «Полка».
DROP SCHEMA IF EXISTS market CASCADE;
CREATE SCHEMA market;
SET search_path TO market, public;

CREATE TABLE categories (
    category_id   integer PRIMARY KEY,
    category_name text NOT NULL,
    parent_id     integer REFERENCES categories(category_id),
    level         smallint NOT NULL    -- 1 корень, 3 лист
);
COMMENT ON TABLE categories IS
  'Иерархия из трёх уровней. Товары привязаны только к листьям (level = 3).';

CREATE TABLE sellers (
    seller_id   integer PRIMARY KEY,
    seller_name text NOT NULL,
    country     text NOT NULL,
    joined_date date NOT NULL,
    tier        text NOT NULL          -- basic / plus / premium
);
COMMENT ON COLUMN sellers.tier IS
  'Тариф продавца. Определяет комиссию: basic 17%, plus 13.5%, premium 10%.';

CREATE TABLE products (
    product_id  integer PRIMARY KEY,
    seller_id   integer NOT NULL REFERENCES sellers(seller_id),
    category_id integer NOT NULL REFERENCES categories(category_id),
    title       text NOT NULL,
    price       numeric(10,2) NOT NULL,
    listed_date date NOT NULL,
    is_active   smallint NOT NULL
);

CREATE TABLE buyers (
    buyer_id    integer PRIMARY KEY,
    country     text,                  -- у части не определена
    signup_date date NOT NULL,
    channel     text NOT NULL
);

CREATE TABLE orders (
    order_id         integer PRIMARY KEY,
    buyer_id         integer NOT NULL REFERENCES buyers(buyer_id),
    created_at       timestamp NOT NULL,
    status           text NOT NULL,    -- delivered / cancelled / returned / in_transit
    payment_method   text NOT NULL,
    delivery_country text,
    promo_code       text,
    shipping_cost    numeric(8,2) NOT NULL
);
COMMENT ON TABLE orders IS
  'Заказ может содержать товары нескольких продавцов. Метрики уровня заказа и уровня позиции — разные.';

CREATE TABLE order_lines (
    order_id       integer NOT NULL REFERENCES orders(order_id),
    product_id     integer NOT NULL REFERENCES products(product_id),
    seller_id      integer NOT NULL REFERENCES sellers(seller_id),
    qty            smallint NOT NULL,
    price          numeric(10,2) NOT NULL,
    commission_pct numeric(4,1) NOT NULL
);
COMMENT ON TABLE order_lines IS
  'Позиции заказа. Первичного ключа нет. price — цена на момент заказа, может отличаться от products.price.';

CREATE TABLE returns (
    return_id     integer PRIMARY KEY,
    order_id      integer NOT NULL REFERENCES orders(order_id),
    product_id    integer NOT NULL REFERENCES products(product_id),
    created_at    timestamp NOT NULL,
    reason        text NOT NULL,
    refund_amount numeric(10,2) NOT NULL
);
COMMENT ON COLUMN returns.refund_amount IS
  'Сумма возврата. У части строк превышает стоимость позиции — это дефект выгрузки.';

CREATE TABLE reviews (
    review_id  integer PRIMARY KEY,
    product_id integer NOT NULL REFERENCES products(product_id),
    buyer_id   integer NOT NULL REFERENCES buyers(buyer_id),
    created_at timestamp NOT NULL,
    rating     smallint NOT NULL,
    has_text   smallint NOT NULL
);
COMMENT ON TABLE reviews IS 'Отзывы. Есть задвоенные: тот же покупатель, товар и дата.';

CREATE INDEX ix_m_prod_seller  ON products(seller_id);
CREATE INDEX ix_m_prod_cat     ON products(category_id);
CREATE INDEX ix_m_ord_buyer    ON orders(buyer_id);
CREATE INDEX ix_m_ord_created  ON orders(created_at);
CREATE INDEX ix_m_ord_status   ON orders(status);
CREATE INDEX ix_m_lines_order  ON order_lines(order_id);
CREATE INDEX ix_m_lines_prod   ON order_lines(product_id);
CREATE INDEX ix_m_lines_seller ON order_lines(seller_id);
CREATE INDEX ix_m_ret_order    ON returns(order_id);
CREATE INDEX ix_m_rev_prod     ON reviews(product_id);
CREATE INDEX ix_m_cat_parent   ON categories(parent_id);
