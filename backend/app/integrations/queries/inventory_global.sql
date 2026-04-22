SELECT
  ib.item AS item_id,
  BUILTIN.DF(ib.item) AS item_name,
  NVL(SUM(ib.quantityOnHand), 0) AS on_hand
FROM InventoryBalance ib
WHERE ib.item IN (%s)
GROUP BY ib.item, BUILTIN.DF(ib.item)
