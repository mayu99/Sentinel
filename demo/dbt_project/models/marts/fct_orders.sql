-- Order facts joined to customer identity, downstream of the broken staging model.
select
    o.order_id,
    o.customer_id,
    c.full_name,
    c.customer_email,
    o.order_total,
    o.status,
    o.ordered_at
from {{ ref('stg_orders') }} o
left join {{ ref('stg_customers') }} c using (customer_id)
