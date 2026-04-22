SELECT
  t.tranid AS so_num,
  BUILTIN.DF(t.entity) AS customer_name,
  BUILTIN.DF(t.custbodyserviceprecis) AS service_type,
  BUILTIN.DF(t.status) AS status_text,
  BUILTIN.DF(t.location) AS location_name,
  tsa.city AS ship_city,
  TO_CHAR(t.custbody10, 'YYYY-MM-DD') AS ship_date
FROM Transaction t
LEFT JOIN transactionShippingAddress tsa ON tsa.nKey = t.shippingAddress
WHERE t.type = 'SalesOrd'
  AND t.tranid = '%s'
