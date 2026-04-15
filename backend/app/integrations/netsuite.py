from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import re
from typing import Any

import requests
from requests_oauthlib import OAuth1

from app.config import Settings

ITEMS_TO_EXCLUDE = {
    2449,
    2447,
    2448,
    2450,
    2446,
    6251,
    6304,
    6299,
    6777,
    6776,
    7014,
    7058,
    1275,
    1276,
    5741,
    2463,
}


@dataclass(frozen=True)
class NetSuiteCredentials:
    consumer_key: str
    consumer_secret: str
    token_id: str
    token_secret: str
    realm: str


def _pick(secret: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = secret.get(key)
        if value:
            return str(value)
    raise ValueError(f"Missing required NetSuite secret key. Tried: {', '.join(keys)}")


def normalize_netsuite_secret(secret_value: str) -> NetSuiteCredentials:
    raw = json.loads(secret_value)
    return NetSuiteCredentials(
        consumer_key=_pick(raw, ["consumerKey", "consumer_key", "clientId", "client_id"]),
        consumer_secret=_pick(raw, ["consumerSecret", "consumer_secret", "clientSecret", "client_secret"]),
        token_id=_pick(raw, ["tokenId", "token_id", "token"]),
        token_secret=_pick(raw, ["tokenSecret", "token_secret"]),
        realm=_pick(raw, ["realm", "account", "accountId"]),
    )


def get_netsuite_credentials(settings: Settings) -> NetSuiteCredentials:
    if all(
        [
            settings.netsuite_client,
            settings.netsuite_secret,
            settings.netsuite_token_id,
            settings.netsuite_token_secret,
            settings.netsuite_realm,
        ]
    ):
        return NetSuiteCredentials(
            consumer_key=str(settings.netsuite_client),
            consumer_secret=str(settings.netsuite_secret),
            token_id=str(settings.netsuite_token_id),
            token_secret=str(settings.netsuite_token_secret),
            realm=str(settings.netsuite_realm),
        )

    if settings.netsuite_secret_name:
        try:
            import boto3
        except ImportError as exc:
            raise ValueError(
                "boto3 is required when NETSUITE_SECRET_NAME is used. "
                "Install boto3 or provide direct NETSUITE_* credentials."
            ) from exc

        client = boto3.client("secretsmanager", region_name=settings.aws_region)
        secret = client.get_secret_value(SecretId=settings.netsuite_secret_name)
        secret_string = secret.get("SecretString")
        if not secret_string:
            raise ValueError("NetSuite secret does not contain SecretString")
        return normalize_netsuite_secret(secret_string)

    raise ValueError(
        "Missing NetSuite credentials. Set either NETSUITE_CLIENT/NETSUITE_SECRET/"
        "NETSUITE_TOKEN_ID/NETSUITE_TOKEN_SECRET/NETSUITE_REALM or NETSUITE_SECRET_NAME."
    )


def build_oauth1(credentials: NetSuiteCredentials) -> OAuth1:
    return OAuth1(
        client_key=credentials.consumer_key,
        client_secret=credentials.consumer_secret,
        resource_owner_key=credentials.token_id,
        resource_owner_secret=credentials.token_secret,
        realm=credentials.realm,
        signature_method="HMAC-SHA256",
    )


def run_suiteql_with_pagination(
    credentials: NetSuiteCredentials,
    query: str,
    params: dict[str, Any],
    page_size: int,
) -> list[dict[str, Any]]:
    endpoint = f"https://{credentials.realm}.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql"
    offset = 0
    all_items: list[dict[str, Any]] = []
    oauth = build_oauth1(credentials)

    while True:
        payload = {"q": query, "params": params, "limit": page_size, "offset": offset}
        response = requests.post(endpoint, json=payload, auth=oauth, timeout=30)
        response.raise_for_status()
        data = response.json()
        items = data.get("items", [])
        all_items.extend(items)
        if len(items) < page_size:
            break
        offset += page_size

    return all_items


LOCATION_SUITEQL = """
SELECT id, name
FROM Location
WHERE isinactive = 'F'
ORDER BY name
"""

SHORTAGE_LINES_SUITEQL = """
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
  AND t.status IN ('SalesOrd:B', 'SalesOrd:D')
  AND tl.mainline = 'F'
  AND tl.taxline = 'F'
  AND tl.shipping = 'F'
  AND tl.cogs = 'F'
  AND t.custbody10 >= TO_DATE(:start_date, 'YYYY-MM-DD')
  AND t.custbody10 <= TO_DATE(:end_date, 'YYYY-MM-DD')
"""

KIT_COMPONENTS_SUITEQL = """
SELECT
  im.parentitem AS kit_item_id,
  im.item AS component_item_id,
  NVL(im.quantity, 0) AS component_qty_per_kit,
  BUILTIN.DF(im.item) AS component_item_name
FROM itemmember im
WHERE im.parentitem IN (%s)
"""

INVENTORY_SUITEQL = """
SELECT
  i.id AS item_id,
  BUILTIN.DF(i.id) AS item_name,
  NVL(il.quantityonhand, 0) AS on_hand
FROM Item i
LEFT JOIN InventoryItemLocation il
  ON il.item = i.id
  AND il.location = :location_id
WHERE i.id IN (%s)
"""

INVENTORY_GLOBAL_SUITEQL = """
SELECT
  i.id AS item_id,
  BUILTIN.DF(i.id) AS item_name,
  NVL(SUM(il.quantityonhand), 0) AS on_hand
FROM Item i
LEFT JOIN InventoryItemLocation il ON il.item = i.id
WHERE i.id IN (%s)
GROUP BY i.id, BUILTIN.DF(i.id)
"""


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    return int(value)


def _item_allowed(item_id: int, item_name: str) -> bool:
    if item_id in ITEMS_TO_EXCLUDE:
        return False
    clean_name = (item_name or "").split(":")[-1].strip()
    if re.match(r"^MOD\s*-", clean_name, re.IGNORECASE):
        return False
    if re.match(r"^Description", clean_name, re.IGNORECASE):
        return False
    prefix_match = re.match(r"^(\d+)", clean_name)
    if prefix_match and int(prefix_match.group(1)) >= 900:
        return False
    return True


def _default_shortage_window() -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    weekday = today.weekday()
    days_until_start = 13 - weekday
    if days_until_start <= 0:
        days_until_start += 7
    start_date = today + timedelta(days=days_until_start)
    end_date = start_date + timedelta(days=14)
    return start_date, end_date


def _format_iso_date(value: date | None) -> str | None:
    if not value:
        return None
    return value.isoformat()


def list_locations(settings: Settings) -> list[dict[str, Any]]:
    credentials = get_netsuite_credentials(settings)
    rows = run_suiteql_with_pagination(
        credentials=credentials,
        query=LOCATION_SUITEQL,
        params={},
        page_size=settings.netsuite_query_page_size,
    )
    return [{"id": _to_int(row.get("id")), "name": str(row.get("name") or "")} for row in rows]


def _fetch_kit_components(
    credentials: NetSuiteCredentials,
    page_size: int,
    kit_item_ids: list[int],
) -> dict[int, list[dict[str, Any]]]:
    if not kit_item_ids:
        return {}
    in_list = ",".join(str(item_id) for item_id in sorted(set(kit_item_ids)))
    rows = run_suiteql_with_pagination(
        credentials=credentials,
        query=KIT_COMPONENTS_SUITEQL % in_list,
        params={},
        page_size=page_size,
    )
    components_by_kit: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        kit_id = _to_int(row.get("kit_item_id"))
        comp_id = _to_int(row.get("component_item_id"))
        comp_name = str(row.get("component_item_name") or "")
        if not _item_allowed(comp_id, comp_name):
            continue
        components_by_kit.setdefault(kit_id, []).append(
            {
                "itemId": comp_id,
                "itemName": comp_name.split(":")[-1].strip(),
                "qtyPerKit": _to_float(row.get("component_qty_per_kit")),
            }
        )
    return components_by_kit


def _fetch_inventory(
    credentials: NetSuiteCredentials,
    page_size: int,
    item_ids: list[int],
    location_id: int | None,
) -> dict[int, dict[str, Any]]:
    if not item_ids:
        return {}

    in_list = ",".join(str(item_id) for item_id in sorted(set(item_ids)))
    query = INVENTORY_SUITEQL if location_id else INVENTORY_GLOBAL_SUITEQL
    params = {"location_id": location_id} if location_id else {}
    rows = run_suiteql_with_pagination(
        credentials=credentials,
        query=query % in_list,
        params=params,
        page_size=page_size,
    )
    return {
        _to_int(row.get("item_id")): {
            "name": str(row.get("item_name") or "").split(":")[-1].strip(),
            "onHand": _to_float(row.get("on_hand")),
        }
        for row in rows
    }


def get_shortage_report(
    settings: Settings,
    location_id: int | None,
    start_date: date | None,
    end_date: date | None,
) -> dict[str, Any]:
    default_start, default_end = _default_shortage_window()
    start = start_date or default_start
    end = end_date or default_end
    credentials = get_netsuite_credentials(settings)

    line_query = SHORTAGE_LINES_SUITEQL
    line_params: dict[str, Any] = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    if location_id:
        line_query += " AND tl.location = :location_id"
        line_params["location_id"] = location_id

    line_rows = run_suiteql_with_pagination(
        credentials=credentials,
        query=line_query,
        params=line_params,
        page_size=settings.netsuite_query_page_size,
    )

    kit_item_ids: list[int] = []
    valid_rows: list[dict[str, Any]] = []
    for row in line_rows:
        item_id = _to_int(row.get("item_id"))
        item_name = str(row.get("item_name") or "")
        if not _item_allowed(item_id, item_name):
            continue
        valid_rows.append(row)
        if str(row.get("is_kit") or "F") == "T":
            kit_item_ids.append(item_id)

    components_by_kit = _fetch_kit_components(credentials, settings.netsuite_query_page_size, kit_item_ids)

    inventory_item_ids: list[int] = []
    for row in valid_rows:
        item_id = _to_int(row.get("item_id"))
        if str(row.get("is_kit") or "F") == "T":
            for component in components_by_kit.get(item_id, []):
                inventory_item_ids.append(component["itemId"])
        else:
            inventory_item_ids.append(item_id)

    inventory = _fetch_inventory(
        credentials=credentials,
        page_size=settings.netsuite_query_page_size,
        item_ids=inventory_item_ids,
        location_id=location_id,
    )

    orders_map: dict[str, dict[str, Any]] = {}
    for row in valid_rows:
        so_num = str(row.get("so_num") or "")
        item_id = _to_int(row.get("item_id"))
        item_name = str(row.get("item_name") or "").split(":")[-1].strip()
        ordered_qty = _to_float(row.get("ordered_qty"))
        is_kit = str(row.get("is_kit") or "F") == "T"
        ship_date = row.get("ship_date")

        if so_num not in orders_map:
            orders_map[so_num] = {
                "soNum": so_num,
                "customer": str(row.get("customer_name") or ""),
                "serviceType": str(row.get("service_type") or ""),
                "date": ship_date,
                "totalOrdered": 0.0,
                "lines": [],
            }
        order_entry = orders_map[so_num]
        order_entry["totalOrdered"] += ordered_qty

        if is_kit:
            shortage_components: list[dict[str, Any]] = []
            for component in components_by_kit.get(item_id, []):
                inv = inventory.get(component["itemId"], {"name": component["itemName"], "onHand": 0.0})
                required_qty = ordered_qty * component["qtyPerKit"]
                remaining = inv["onHand"] - required_qty
                if inv["onHand"] < required_qty:
                    shortage_components.append(
                        {
                            "itemId": component["itemId"],
                            "itemName": inv["name"],
                            "orderedQty": required_qty,
                            "onHandQty": inv["onHand"],
                            "remainingStock": remaining,
                        }
                    )
            if shortage_components:
                order_entry["lines"].append(
                    {
                        "itemId": item_id,
                        "itemName": item_name,
                        "date": ship_date,
                        "orderedQty": ordered_qty,
                        "isKit": True,
                        "components": shortage_components,
                    }
                )
            continue

        inv = inventory.get(item_id, {"name": item_name, "onHand": 0.0})
        remaining = inv["onHand"] - ordered_qty
        if inv["onHand"] < ordered_qty:
            order_entry["lines"].append(
                {
                    "itemId": item_id,
                    "itemName": inv["name"],
                    "date": ship_date,
                    "orderedQty": ordered_qty,
                    "onHandQty": inv["onHand"],
                    "remainingStock": remaining,
                    "isKit": False,
                    "components": [],
                }
            )

    orders = [order for order in orders_map.values() if order["lines"]]
    orders.sort(key=lambda entry: (entry["date"] or "9999-12-31", entry["soNum"]))

    return {
        "locationId": location_id,
        "startDate": _format_iso_date(start),
        "endDate": _format_iso_date(end),
        "orders": orders,
        "totalOrders": len(orders),
        "asOf": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
