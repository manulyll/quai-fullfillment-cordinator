SELECT
  t.id AS so_id,
  t.tranid AS so_num,
  BUILTIN.DF(t.entity) AS customer_name,
  COALESCE(ce.event_status, BUILTIN.DF(t.status)) AS status_text,
  TO_CHAR(t.custbody10, 'YYYY-MM-DD') AS ship_date,
  COALESCE(BUILTIN.DF(t.location), BUILTIN.DF(tll.location_id)) AS location_name
FROM Transaction t
LEFT JOIN (
  SELECT
    transaction,
    MAX(status) AS event_status
  FROM calendarEvent
  GROUP BY transaction
) ce ON ce.transaction = t.id
LEFT JOIN (
  SELECT
    transaction,
    MAX(location) AS location_id
  FROM TransactionLine
  WHERE mainline = 'F'
    AND taxline = 'F'
  GROUP BY transaction
) tll ON tll.transaction = t.id
WHERE t.type = 'SalesOrd'
  AND t.custbody10 = TO_DATE('%s', 'YYYY-MM-DD')
