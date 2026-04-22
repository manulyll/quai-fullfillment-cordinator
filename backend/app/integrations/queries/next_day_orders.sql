SELECT
  t.id AS so_id,
  t.tranid AS so_num,
  BUILTIN.DF(t.entity) AS customer_name,
  BUILTIN.DF(t.status) AS status_text,
  TO_CHAR(t.custbody10, 'YYYY-MM-DD') AS ship_date,
  BUILTIN.DF(t.location) AS location_name
FROM Transaction t
WHERE t.type = 'SalesOrd'
  AND t.custbody10 = TO_DATE('%s', 'YYYY-MM-DD')
