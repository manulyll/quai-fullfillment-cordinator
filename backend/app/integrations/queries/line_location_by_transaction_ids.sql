SELECT
  transaction AS so_id,
  location AS location_id,
  BUILTIN.DF(location) AS location_name
FROM TransactionLine
WHERE transaction IN (%s)
  AND mainline = 'F'
  AND taxline = 'F'
