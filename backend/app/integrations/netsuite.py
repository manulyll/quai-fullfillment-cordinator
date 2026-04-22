from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import time
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
    headers = {"Prefer": "transient", "Content-Type": "application/json", "Accept": "application/json"}

    while True:
        payload: dict[str, Any] = {"q": query}
        if params:
            payload["params"] = params
        response = requests.post(
            endpoint,
            params={"limit": page_size, "offset": offset},
            json=payload,
            auth=oauth,
            headers=headers,
            timeout=30,
        )
        if not response.ok:
            raise ValueError(f"NetSuite query failed ({response.status_code}): {response.text}")
        data = response.json()
        items = data.get("items", [])
        all_items.extend(items)
        if len(items) < page_size:
            break
        offset += page_size

    return all_items


QUERIES_DIR = Path(__file__).resolve().parent / "queries"


def _read_query(filename: str) -> str:
    return (QUERIES_DIR / filename).read_text(encoding="utf-8").strip()


LOCATION_SUITEQL = _read_query("location.sql")
SHORTAGE_LINES_SUITEQL = _read_query("shortage_lines.sql")
KIT_COMPONENTS_SUITEQL = _read_query("kit_components.sql")
INVENTORY_SUITEQL = _read_query("inventory_by_location.sql")
INVENTORY_GLOBAL_SUITEQL = _read_query("inventory_global.sql")
NEXT_DAY_ORDERS_SUITEQL = _read_query("next_day_orders.sql")
PICKING_TICKET_HEADER_SUITEQL = _read_query("picking_ticket_header.sql")
PICKING_TICKET_LINES_SUITEQL = _read_query("picking_ticket_lines.sql")


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


_verified_ddb_tables: set[str] = set()


def _cache_key(prefix: str, payload: dict[str, Any]) -> str:
    fingerprint = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def _get_ddb_table(settings: Settings):
    if not settings.netsuite_ddb_cache_enabled or not settings.netsuite_ddb_cache_table:
        return None
    try:
        import boto3
        from botocore.exceptions import ClientError
    except Exception:
        return None

    table_name = settings.netsuite_ddb_cache_table
    try:
        dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        table = dynamodb.Table(table_name)
        if table_name in _verified_ddb_tables:
            return table

        try:
            table.load()
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code not in {"ResourceNotFoundException", "ValidationException"}:
                return None
            try:
                dynamodb.meta.client.create_table(
                    TableName=table_name,
                    KeySchema=[{"AttributeName": "cache_key", "KeyType": "HASH"}],
                    AttributeDefinitions=[{"AttributeName": "cache_key", "AttributeType": "S"}],
                    BillingMode="PAY_PER_REQUEST",
                )
                dynamodb.meta.client.get_waiter("table_exists").wait(TableName=table_name)
            except Exception:
                return None

        _verified_ddb_tables.add(table_name)
        return table
    except Exception:
        return None


def _cache_get(settings: Settings, key: str) -> dict[str, Any] | list[dict[str, Any]] | None:
    table = _get_ddb_table(settings)
    if table is None:
        return None
    try:
        response = table.get_item(Key={"cache_key": key}, ConsistentRead=False)
        item = response.get("Item")
        if not item:
            return None
        now = int(time.time())
        if int(item.get("expires_at", 0)) <= now:
            return None
        payload = item.get("payload")
        if not isinstance(payload, str):
            return None
        return json.loads(payload)
    except Exception:
        return None


def _cache_set(settings: Settings, key: str, value: dict[str, Any] | list[dict[str, Any]]) -> None:
    table = _get_ddb_table(settings)
    if table is None:
        return
    try:
        payload = json.dumps(value, separators=(",", ":"), default=str)
        if len(payload.encode("utf-8")) > settings.netsuite_ddb_cache_max_payload_bytes:
            return
        now = int(time.time())
        ttl = max(settings.netsuite_query_cache_ttl_seconds, 60)
        table.put_item(
            Item={
                "cache_key": key,
                "expires_at": now + ttl,
                "updated_at": now,
                "payload": payload,
            }
        )
    except Exception:
        return


def list_locations(settings: Settings) -> list[dict[str, Any]]:
    key = _cache_key("locations:v1", {"realm": settings.netsuite_realm or settings.netsuite_secret_name or "unknown"})
    cached = _cache_get(settings, key)
    if isinstance(cached, list):
        return cached

    credentials = get_netsuite_credentials(settings)
    rows = run_suiteql_with_pagination(
        credentials=credentials,
        query=LOCATION_SUITEQL,
        params={},
        page_size=settings.netsuite_query_page_size,
    )
    result = [{"id": _to_int(row.get("id")), "name": str(row.get("name") or "")} for row in rows]
    _cache_set(settings, key, result)
    return result


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
    query = (INVENTORY_SUITEQL % (int(location_id), in_list)) if location_id else (INVENTORY_GLOBAL_SUITEQL % in_list)
    params: dict[str, Any] = {}
    rows = run_suiteql_with_pagination(
        credentials=credentials,
        query=query,
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

    line_query = (
        SHORTAGE_LINES_SUITEQL
        + f"\n  AND t.custbody10 >= TO_DATE('{start.isoformat()}', 'YYYY-MM-DD')"
        + f"\n  AND t.custbody10 <= TO_DATE('{end.isoformat()}', 'YYYY-MM-DD')"
    )
    line_params: dict[str, Any] = {}
    if location_id:
        line_query += f"\n  AND tl.location = {int(location_id)}"

    report_cache_key = _cache_key(
        "shortage-report:v2",
        {
            "realm": settings.netsuite_realm or settings.netsuite_secret_name or "unknown",
            "location_id": location_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
    )
    cached_report = _cache_get(settings, report_cache_key)
    if isinstance(cached_report, dict):
        return cached_report

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
                "status": str(row.get("status_text") or ""),
                "location": str(row.get("location_name") or ""),
                "city": "",
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

    payload = {
        "locationId": location_id,
        "startDate": _format_iso_date(start),
        "endDate": _format_iso_date(end),
        "orders": orders,
        "totalOrders": len(orders),
        "asOf": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    _cache_set(settings, report_cache_key, payload)
    return payload


def get_next_day_orders(settings: Settings, target_date: date | None = None, location_id: int | None = None) -> dict[str, Any]:
    effective_date = target_date or (datetime.now(timezone.utc).date() + timedelta(days=1))
    cache_key = _cache_key(
        "next-day-orders:v2",
        {
            "realm": settings.netsuite_realm or settings.netsuite_secret_name or "unknown",
            "date": effective_date.isoformat(),
            "location_id": location_id,
        },
    )
    cached_payload = _cache_get(settings, cache_key)
    if isinstance(cached_payload, dict):
        return cached_payload

    credentials = get_netsuite_credentials(settings)
    query = NEXT_DAY_ORDERS_SUITEQL % effective_date.isoformat()
    if location_id:
        query += f"\n  AND t.location = {int(location_id)}"
    query += "\nORDER BY t.tranid"
    rows = run_suiteql_with_pagination(
        credentials=credentials,
        query=query,
        params={},
        page_size=settings.netsuite_query_page_size,
    )
    orders: list[dict[str, Any]] = []
    unconfirmed = 0
    for row in rows:
        status = str(row.get("status_text") or "")
        confirmed = "confirm" in status.lower()
        if not confirmed:
            unconfirmed += 1
        orders.append(
            {
                "soNum": str(row.get("so_num") or ""),
                "customer": str(row.get("customer_name") or ""),
                "status": status,
                "isConfirmed": confirmed,
                "shipDate": str(row.get("ship_date") or ""),
                "location": str(row.get("location_name") or ""),
            }
        )

    payload = {
        "date": effective_date.isoformat(),
        "totalOrders": len(orders),
        "unconfirmedOrders": unconfirmed,
        "orders": orders,
        "asOf": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    _cache_set(settings, cache_key, payload)
    return payload


def get_picking_ticket_html(settings: Settings, so_num: str) -> str:
    normalized_so = so_num.strip().upper()
    if not normalized_so:
        raise ValueError("Sales order number is required")

    cache_key = _cache_key(
        "picking-ticket:v1",
        {"realm": settings.netsuite_realm or settings.netsuite_secret_name or "unknown", "so_num": normalized_so},
    )
    cached = _cache_get(settings, cache_key)
    if isinstance(cached, dict) and isinstance(cached.get("html"), str):
        return str(cached["html"])

    credentials = get_netsuite_credentials(settings)
    header_rows = run_suiteql_with_pagination(
        credentials=credentials,
        query=PICKING_TICKET_HEADER_SUITEQL % normalized_so,
        params={},
        page_size=settings.netsuite_query_page_size,
    )
    if not header_rows:
        raise ValueError(f"Sales order {normalized_so} not found")
    header = header_rows[0]
    line_rows = run_suiteql_with_pagination(
        credentials=credentials,
        query=PICKING_TICKET_LINES_SUITEQL % normalized_so,
        params={},
        page_size=settings.netsuite_query_page_size,
    )
    filtered_lines = []
    for row in line_rows:
        item_id = _to_int(row.get("item_id"))
        item_name = str(row.get("item_name") or "")
        if not _item_allowed(item_id, item_name):
            continue
        qty = _to_float(row.get("ordered_qty"))
        if qty <= 0:
            continue
        filtered_lines.append((item_name.split(":")[-1].strip(), qty))

    rows_html = "".join(
        f"<tr><td>{name}</td><td style='text-align:right'>{qty:g}</td><td></td></tr>" for name, qty in filtered_lines
    )
    html = f"""<!doctype html>
<html>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>Picking Ticket {normalized_so}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 12px; color: #1f2937; }}
    .sheet {{ max-width: 920px; margin: 0 auto; }}
    .head {{ display:flex; justify-content:space-between; align-items:center; gap: 12px; }}
    .meta {{ display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap:8px; margin:12px 0; }}
    .meta div {{ background:#f8fafc; border:1px solid #e5e7eb; border-radius:8px; padding:8px; }}
    table {{ width:100%; border-collapse: collapse; }}
    th, td {{ border:1px solid #d1d5db; padding:8px; font-size:14px; }}
    th {{ background:#f3f4f6; text-align:left; }}
    .actions {{ display:flex; gap:8px; margin:12px 0; }}
    button {{ border:none; border-radius:8px; padding:10px 14px; background:#4b5563; color:white; cursor:pointer; }}
    @media (max-width: 640px) {{ body {{ margin: 6px; }} th, td {{ font-size: 12px; padding: 6px; }} }}
    @page {{ size: Letter portrait; margin: 0.4in; }}
    @media print {{ .actions {{ display:none; }} body {{ margin: 0; }} }}
  </style>
</head>
<body>
  <div class='sheet'>
    <div class='head'>
      <h1>Picking Ticket - {normalized_so}</h1>
      <span>{datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}</span>
    </div>
    <div class='actions'>
      <button onclick='window.print()'>Print (8.5 x 11)</button>
    </div>
    <div class='meta'>
      <div><strong>Customer:</strong> {str(header.get("customer_name") or "-")}</div>
      <div><strong>Ship Date:</strong> {str(header.get("ship_date") or "-")}</div>
      <div><strong>Service Type:</strong> {str(header.get("service_type") or "-")}</div>
      <div><strong>Status:</strong> {str(header.get("status_text") or "-")}</div>
      <div><strong>Location:</strong> {str(header.get("location_name") or "-")}</div>
      <div><strong>City:</strong> -</div>
    </div>
    <table>
      <thead><tr><th>Item</th><th style='text-align:right'>Qty</th><th>Picked</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</body>
</html>"""
    _cache_set(settings, cache_key, {"html": html})
    return html
