-- Staging model for customers.
-- BROKEN ON PURPOSE: upstream renamed customer_email -> email on 2026-08-07,
-- but this model was never updated. The nightly run fails here.
select
    customer_id,
    full_name,
    customer_email,          -- <- column no longer exists in public.customers
    signup_source,
    created_at
from public.customers
