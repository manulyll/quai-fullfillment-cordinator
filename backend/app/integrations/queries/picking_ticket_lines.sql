SELECT
  tl.item AS item_id,
  BUILTIN.DF(tl.item) AS item_name,
  ABS(NVL(tl.quantity, 0)) AS ordered_qty
FROM Transaction t
JOIN TransactionLine tl ON tl.transaction = t.id
WHERE t.type = 'SalesOrd'
  AND t.tranid = '%s'
  AND tl.mainline = 'F'
  AND tl.taxline = 'F'
ORDER BY tl.id
