SELECT
  t.tranid AS so_num,
  BUILTIN.DF(t.entity) AS customer_name,
  BUILTIN.DF(t.custbodyserviceprecis) AS service_type,
  BUILTIN.DF(t.status) AS status_text,
  COALESCE(BUILTIN.DF(t.location), BUILTIN.DF(tll.location_id)) AS location_name,
  tsa.addressee AS ship_addressee,
  tsa.addr1 AS ship_addr1,
  tsa.addr2 AS ship_addr2,
  tsa.addr3 AS ship_addr3,
  tsa.city AS ship_city,
  tsa.state AS ship_state,
  tsa.zip AS ship_zip,
  tsa.country AS ship_country,
  TO_CHAR(t.custbody10, 'YYYY-MM-DD') AS ship_date
FROM Transaction t
LEFT JOIN (
  SELECT
    transaction,
    MAX(location) AS location_id
  FROM TransactionLine
  WHERE mainline = 'F'
    AND taxline = 'F'
  GROUP BY transaction
) tll ON tll.transaction = t.id
LEFT JOIN transactionShippingAddress tsa ON tsa.nKey = t.shippingAddress
WHERE t.type = 'SalesOrd'
  AND t.tranid = '%s'
