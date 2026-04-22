SELECT
  im.parentitem AS kit_item_id,
  im.item AS component_item_id,
  NVL(im.quantity, 0) AS component_qty_per_kit,
  BUILTIN.DF(im.item) AS component_item_name
FROM itemmember im
WHERE im.parentitem IN (%s)
