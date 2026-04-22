SELECT
  t.tranid AS so_num,
  BUILTIN.DF(t.entity) AS customer_name,
  BUILTIN.DF(t.custbodyserviceprecis) AS service_type,
  BUILTIN.DF(t.status) AS status_text,
  BUILTIN.DF(t.location) AS location_name,
  TO_CHAR(t.custbody10, 'YYYY-MM-DD') AS ship_date
FROM Transaction t
WHERE t.type = 'SalesOrd'
  AND t.tranid = '%s'
