SELECT
  i.id AS item_id,
  BUILTIN.DF(i.id) AS item_name,
  NVL(SUM(ail.quantityonhand), 0) AS on_hand
FROM Item i
LEFT JOIN AggregateItemLocation ail ON ail.item = i.id
WHERE i.id IN (%s)
GROUP BY i.id, BUILTIN.DF(i.id)
