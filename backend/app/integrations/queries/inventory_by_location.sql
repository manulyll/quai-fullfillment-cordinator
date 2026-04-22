SELECT
  i.id AS item_id,
  BUILTIN.DF(i.id) AS item_name,
  NVL(ail.quantityonhand, 0) AS on_hand
FROM Item i
LEFT JOIN AggregateItemLocation ail
  ON ail.item = i.id
  AND ail.location = %s
WHERE i.id IN (%s)
