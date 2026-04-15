from utils import query_netsuite
import json
import requests


TEST_QUERIES = {
    "locations": """
        SELECT id, name
        FROM Location
        WHERE isinactive = 'F'
        ORDER BY name
    """,
    "sales_lines_smoke": """
        SELECT
          t.tranid AS so_num,
          BUILTIN.DF(t.entity) AS customer_name,
          TO_CHAR(t.custbody10, 'YYYY-MM-DD') AS ship_date,
          tl.item AS item_id,
          BUILTIN.DF(tl.item) AS item_name,
          NVL(tl.quantity, 0) AS ordered_qty
        FROM Transaction t
        JOIN TransactionLine tl ON tl.transaction = t.id
        WHERE t.type = 'SalesOrd'
          AND tl.mainline = 'F'
          AND tl.taxline = 'F'
          AND t.custbody10 IS NOT NULL
          AND t.trandate >= CURRENT_DATE - 30
        ORDER BY t.tranid DESC
    """,
    "backend_shortage_line_query_smoke": """
        SELECT
          t.id AS so_id,
          t.tranid AS so_num,
          BUILTIN.DF(t.entity) AS customer_name,
          BUILTIN.DF(t.custbodyserviceprecis) AS service_type,
          TO_CHAR(t.custbody10, 'YYYY-MM-DD') AS ship_date,
          tl.id AS line_id,
          tl.item AS item_id,
          BUILTIN.DF(tl.item) AS item_name,
          NVL(tl.quantity, 0) AS ordered_qty,
          CASE WHEN i.itemtype = 'Kit' THEN 'T' ELSE 'F' END AS is_kit
        FROM Transaction t
        JOIN TransactionLine tl ON tl.transaction = t.id
        JOIN Item i ON i.id = tl.item
        WHERE t.type = 'SalesOrd'
          AND tl.mainline = 'F'
          AND tl.taxline = 'F'
          AND t.custbody10 IS NOT NULL
          AND t.trandate >= CURRENT_DATE - 30
        ORDER BY t.tranid DESC
    """,
    "itemmember_smoke": """
        SELECT
          im.parentitem AS kit_item_id,
          im.item AS component_item_id,
          NVL(im.quantity, 0) AS component_qty_per_kit,
          BUILTIN.DF(im.item) AS component_item_name
        FROM itemmember im
    """,
    "item_onhand_smoke": """
        SELECT
          i.id AS item_id,
          BUILTIN.DF(i.id) AS item_name,
          NVL(i.quantityonhand, 0) AS on_hand
        FROM Item i
        WHERE i.id IS NOT NULL
    """,
}


def run_query(name: str, query: str) -> None:
    print(f"\n=== Running query: {name} ===")
    try:
        response = query_netsuite(query, limit=50, offset=0, fetch_all=False)
    except requests.HTTPError as exc:
        print(f"HTTP error: {exc}")
        if exc.response is not None:
            print(exc.response.text)
        raise
    items = response.get("items", [])
    print(f"Rows: {len(items)}")
    if items:
        preview = items[:3]
        print(json.dumps(preview, indent=2))
    else:
        print("No rows returned.")


def main() -> None:
    for name, query in TEST_QUERIES.items():
        run_query(name, query)


if __name__ == "__main__":
    main()