-- Sentinel demo warehouse.
-- Simulates the state of the warehouse AFTER an upstream team shipped a
-- breaking change: raw.customers used to have `customer_email`, but a
-- source-system migration renamed it to `email` (and added `email_verified`).
-- The dbt model stg_customers.sql still selects `customer_email`, so the
-- nightly run fails. Sentinel's job is to discover this by inspecting the
-- live schema — not by being told.

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS analytics;

DROP TABLE IF EXISTS raw.customers;
CREATE TABLE raw.customers (
    customer_id     BIGINT PRIMARY KEY,
    full_name       TEXT        NOT NULL,
    email           TEXT        NOT NULL,   -- was: customer_email (renamed 2026-08-07)
    email_verified  BOOLEAN     NOT NULL DEFAULT FALSE,
    signup_source   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    _loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TABLE IF EXISTS raw.orders;
CREATE TABLE raw.orders (
    order_id     BIGINT PRIMARY KEY,
    customer_id  BIGINT      NOT NULL,
    order_total  NUMERIC(10,2) NOT NULL,
    status       TEXT        NOT NULL,
    ordered_at   TIMESTAMPTZ NOT NULL,
    _loaded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO raw.customers (customer_id, full_name, email, email_verified, signup_source, created_at) VALUES
  (1, 'Ada Lovelace',    'ada@example.com',    TRUE,  'organic',  now() - interval '90 days'),
  (2, 'Grace Hopper',    'grace@example.com',  TRUE,  'referral', now() - interval '60 days'),
  (3, 'Edsger Dijkstra', 'edsger@example.com', FALSE, 'paid',     now() - interval '30 days'),
  (4, 'Barbara Liskov',  'barbara@example.com',TRUE,  'organic',  now() - interval '10 days');

INSERT INTO raw.orders (order_id, customer_id, order_total, status, ordered_at) VALUES
  (101, 1, 129.00, 'completed', now() - interval '9 days'),
  (102, 2,  49.50, 'completed', now() - interval '7 days'),
  (103, 2, 220.00, 'refunded',  now() - interval '5 days'),
  (104, 3,  15.75, 'completed', now() - interval '2 days'),
  (105, 4,  88.20, 'pending',   now() - interval '6 hours');
