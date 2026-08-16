# Incident Report: stg_customers failure

## Summary
The `stg_customers` model failed because it references a column `customer_email` that no longer exists in the source table `raw.customers`.

## Evidence
Upstream columns in `raw.customers`: customer_id, full_name, contact_email, email_verified, signup_source, created_at.

## Root Cause
Upstream table `raw.customers` renamed `customer_email` to `contact_email`; `stg_customers.sql` still selects `customer_email`.

## Proposed Fix
Update `models/staging/stg_customers.sql` to select `contact_email` instead of `customer_email`.

## Guardrail
Implement a dbt model contract in `models/staging/stg_customers.yml` to enforce the presence of required columns.