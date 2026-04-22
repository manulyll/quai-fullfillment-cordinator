SELECT
  t.id AS so_id,
  t.tranid AS so_num,
  BUILTIN.DF(t.entity) AS customer_name,
  BUILTIN.DF(t.custbodyserviceprecis) AS service_type,
  BUILTIN.DF(t.status) AS status_text,
  BUILTIN.DF(tl.location) AS location_name,
  tsa.city AS ship_city,
  TO_CHAR(t.custbody10, 'YYYY-MM-DD') AS ship_date,
  tl.id AS line_id,
  tl.item AS item_id,
  BUILTIN.DF(tl.item) AS item_name,
  ABS(NVL(tl.quantity, 0)) AS ordered_qty,
  CASE WHEN i.itemtype = 'Kit' THEN 'T' ELSE 'F' END AS is_kit
FROM Transaction t
JOIN TransactionLine tl ON tl.transaction = t.id
JOIN Item i ON i.id = tl.item
LEFT JOIN transactionShippingAddress tsa ON tsa.nKey = t.shippingAddress
WHERE t.type = 'SalesOrd'
  AND tl.mainline = 'F'
  AND tl.taxline = 'F'
  AND t.custbody10 >= TO_DATE('2026-04-01', 'YYYY-MM-DD')
