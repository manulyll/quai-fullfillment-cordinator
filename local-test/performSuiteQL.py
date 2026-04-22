from pathlib import Path
from utils import query_netsuite
import json
import requests

QUERIES_DIR = Path(__file__).resolve().parents[1] / "backend" / "app" / "integrations" / "queries"


def read_query(name: str) -> str:
    return (QUERIES_DIR / name).read_text(encoding="utf-8").strip()


TEST_QUERIES = {
    "locations": read_query("location.sql"),
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
          AND t.custbody10 >= TO_DATE('2026-04-01', 'YYYY-MM-DD')
        ORDER BY t.tranid DESC
    """,
    "backend_shortage_line_query_smoke": read_query("shortage_lines.sql") + "\nORDER BY t.tranid DESC",
    "itemmember_smoke": read_query("kit_components.sql").replace("WHERE im.parentitem IN (%s)", "WHERE im.parentitem IS NOT NULL"),
    "item_onhand_smoke": """
        SELECT
          ib.item AS item_id,
          BUILTIN.DF(ib.item) AS item_name,
          ib.location AS location_id,
          BUILTIN.DF(ib.location) AS location_name,
          NVL(ib.quantityOnHand, 0) AS on_hand
        FROM InventoryBalance ib
        WHERE NVL(ib.quantityOnHand, 0) > 0
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