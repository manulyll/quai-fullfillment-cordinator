import hashlib
import hmac
import json
import requests
import base64
import time
import random
import urllib.parse
import pytz
import datetime 
from requests_oauthlib import OAuth1
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import re
from collections import defaultdict
import os
import html
from decimal import Decimal, ROUND_HALF_UP
import pathlib as Path
import xml.etree.ElementTree as ET
from xml.dom import minidom
from decimal import Decimal, ROUND_HALF_UP
import urllib3
http = urllib3.PoolManager()
import paramiko
import io
from pathlib import PurePosixPath

_cached_secrets = None
_cached_queries = None
_cached_payloads_scale = None

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
def get_local_path(filename):
    return os.path.join(CURRENT_DIR, filename)


def get_secrets():
    global _cached_secrets
    if _cached_secrets is None:
        with open(get_local_path("secrets.json"), "r") as f:
            _cached_secrets = json.load(f)
    return _cached_secrets

def get_queries():
    global _cached_queries
    if _cached_queries is None:
        with open(get_local_path("queries.json"), "r") as f:
            _cached_queries = json.load(f)
    return _cached_queries

def get_payloads_scale():
    global _cached_payloads_scale
    if _cached_payloads_scale is None:
        with open(get_local_path("payloads-scale.json"), "r") as f:
            _cached_payloads_scale = json.load(f)
    return _cached_payloads_scale

def load_xml_template(file_path):
    with open(get_local_path(file_path), 'r', encoding='utf-8') as file:
        return file.read()

def generate_timestamp():
    """Generate the current timestamp."""
    return str(int(time.time()))

def generate_nonce(length=11):
    """Generate a pseudorandom nonce."""
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])


def generate_signature(method, url, params, consumer_key, nonce, timestamp, token, consumer_secret, token_secret):
    # OAuth-specific params (added automatically)
    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_token": token,
        "oauth_nonce": nonce,
        "oauth_timestamp": timestamp,
        "oauth_signature_method": "HMAC-SHA256",
        "oauth_version": "1.0"
    }

    # Merge user-provided query params and OAuth params
    all_params = {**params, **oauth_params}

    # Sort & percent-encode params
    sorted_items = sorted((urllib.parse.quote_plus(str(k)), urllib.parse.quote_plus(str(v))) for k, v in all_params.items())
    param_string = '&'.join(f"{k}={v}" for k, v in sorted_items)

    # Construct the OAuth base string
    base_string = '&'.join([
        method.upper(),
        urllib.parse.quote(url, safe=''),
        urllib.parse.quote(param_string, safe='')
    ])

    # Construct the signing key
    signing_key = f"{urllib.parse.quote(consumer_secret)}&{urllib.parse.quote(token_secret)}"

    # HMAC-SHA256 signing
    hashed = hmac.new(signing_key.encode('utf-8'), base_string.encode('utf-8'), hashlib.sha256)
    signature = base64.b64encode(hashed.digest()).decode('utf-8')

    return signature

def query_netsuite(sql_query, limit=1000, offset=0, fetch_all=True):
    """
    Execute a SuiteQL query and return **all** results, transparently
    handling pagination using limit/offset.
    """
    secrets = get_secrets()

    ns_account_id = secrets["realmId"]
    consumer_key = secrets.get("nsDownloadClient") or secrets.get("Client")
    consumer_secret = secrets.get("nsDownloadSecret") or secrets.get("Secret")
    token = secrets.get("nsDownloadTokenId") or secrets.get("TokenId")
    token_secret = secrets.get("nsDownloadTokenSecret") or secrets.get("TokenSecret")
    base_url = secrets["nsQueryUrl"]

    if not all([consumer_key, consumer_secret, token, token_secret]):
        raise ValueError(
            "Missing NetSuite OAuth keys in secrets.json. "
            "Expected either nsDownload* keys or Client/Secret/TokenId/TokenSecret."
        )

    all_items = []
    current_offset = offset
    total_results = None
    first_response = None

    while True:
        params = {
            "limit": limit,
            "offset": current_offset
        }
        url_with_params = f"{base_url}?{urllib.parse.urlencode(params)}"

        # OAuth signature components
        nonce = generate_nonce()
        timestamp = generate_timestamp()

        signature = generate_signature(
            method="POST",
            url=base_url,         # Base URL only, no params
            params=params,        # Query params to be included in signature
            consumer_key=consumer_key,
            nonce=nonce,
            timestamp=timestamp,
            token=token,
            consumer_secret=consumer_secret,
            token_secret=token_secret
        )

        # Construct OAuth header
        oauth_header = (
            f'OAuth realm="{ns_account_id}", '
            f'oauth_consumer_key="{consumer_key}", '
            f'oauth_token="{token}", '
            f'oauth_signature_method="HMAC-SHA256", '
            f'oauth_timestamp="{timestamp}", '
            f'oauth_nonce="{nonce}", '
            f'oauth_version="1.0", '
            f'oauth_signature="{urllib.parse.quote(signature)}"'
        )

        # Set headers
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "transient",
            "Authorization": oauth_header
        }

        # Query payload
        payload = json.dumps({
            "q": sql_query
        })

        # Send the POST request to SuiteQL endpoint
        response = requests.post(url_with_params, headers=headers, data=payload)

        # Raise error if response failed
        response.raise_for_status()

        page = response.json()

        # Capture metadata from the first page so we can return
        # a response that looks like NetSuite's, but with all items.
        if first_response is None:
            first_response = dict(page)  # shallow copy

        items = page.get("items", []) or []
        all_items.extend(items)

        # Determine totalResults, if provided
        if total_results is None:
            total_results = page.get("totalResults")

        # Stop when we have fewer than `limit` items or we've reached totalResults
        if not fetch_all:
            break
        if len(items) < limit:
            break
        if total_results is not None and (current_offset + len(items)) >= total_results:
            break

        current_offset += len(items)

    if first_response is None:
        # No data at all (e.g., empty result)
        return {"items": [], "offset": offset, "totalResults": 0, "count": 0}

    # Build combined response
    combined = dict(first_response)
    combined["items"] = all_items
    combined["offset"] = offset
    combined["count"] = len(all_items)
    if total_results is not None:
        combined["totalResults"] = total_results
    else:
        combined["totalResults"] = len(all_items)

    return combined

def getScaleBearerToken():
    # Load secrets from JSON file
    secrets = get_secrets()

    url = f"https://login.microsoftonline.com/{secrets['TenantID']}/oauth2/token"

    payload = {
        'grant_type': 'client_credentials',
        'client_id': secrets['APIConfidentialClientID'],
        'client_secret': secrets['APIConfidentialSecret'],
        'resource': secrets['ClientID']
    }

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    # Send a POST request
    response = requests.post(url, data=payload, headers=headers)

# Check for errors
    if response.status_code == 200:
        return response.json()["access_token"]  # ✅ Correct way to extract access_token
    else:
        print(f"Error: {response.status_code}, {response.text}")
        return None

def post_to_scale_api(endpoint, payload, content_type="json"):
    # Load secrets from JSON file
    secrets = get_secrets()

    # Determine the base URL dynamically
    if content_type == "json":
        base_url = f"https://{secrets['scaleURL']}/general/scaleapi/InterfacesApi/{endpoint}"
    else:  # XML case
        base_url = f"https://{secrets['scaleURL']}/general/interfaces/{endpoint}"

    print(f"Posting to Scale API at {base_url} with content type {content_type}")

    # Get Scale Token
    token = getScaleBearerToken()
    if not token:
        raise ValueError("Failed to retrieve access token.")

    # Set request headers dynamically based on content type
    headers = {
        "Authorization": f"Bearer {token}",
        "environment": secrets["Environment"],
        "warehouse": secrets["Warehouse"],
        "Accept": "application/json" if content_type == "json" else "application/xml"
    }

    if content_type == "json":
        headers["Content-Type"] = "application/json"
        if isinstance(payload, (list, dict)):
            payload = json.dumps(payload)  # Convert dict to JSON string
    else:  # XML Handling
        headers["Content-Type"] = "application/xml"
        if not isinstance(payload, str):
            raise ValueError("XML payload must be a raw string.")

    # Send the request
    response = requests.post(base_url, headers=headers, data=payload)
    print(f"resonse: {response}")  

    # Handle response
    if response.status_code == 200:
        if content_type == "json":
            try:
                return response.status_code, response.json()  # Return JSON response
            except json.JSONDecodeError:
                return response.status_code, response.text  # Return raw text if not valid JSON
        else:
            return response.status_code, response.text  # XML response (raw text)
    else:
        return response.status_code, response.text  # Always return status and response body

def get_timestamp_minutes_ago(minutes):
    """
    Returns a formatted timestamp string for X minutes ago in Eastern timezone.
    
    Args:
        minutes (int): Number of minutes to subtract from current time
    
    Returns:
        str: Formatted timestamp string in format 'YYYY-MM-DD HH:MM:SS.000000000'
    """
    eastern = pytz.timezone('US/Eastern')
    current_time_eastern = datetime.datetime.now(eastern)
    time_ago = current_time_eastern - datetime.timedelta(minutes=minutes)
    timestamp_str = time_ago.strftime('%Y-%m-%d %H:%M:%S.000000000')
    return timestamp_str

def replace_placeholders(obj, data_dict):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                replace_placeholders(value, data_dict)
            elif isinstance(value, str) and "{" in value and "}" in value:
                # Extract field names from placeholder {fieldname}
                field_names = re.findall(r'\{([^}]+)\}', value)
                new_value = value

                for field_name in field_names:
                    placeholder = "{" + field_name + "}"
                    if field_name in data_dict and data_dict[field_name] is not None:
                        replacement = str(data_dict[field_name])
                        
                        # 🟡 Special case for "companyname"
                        if field_name == "companyname":
                            replacement = replacement[:25]
                        if field_name == "otherrefnum":
                            replacement = replacement[:25]
                        if field_name == "memo":
                            replacement = replacement[:25]
                        if field_name == "custitem1":
                            replacement = replacement[:25]
                        if field_name == "custitem_retailer_item_num":
                            replacement = replacement[:25]

                        new_value = new_value.replace(placeholder, replacement)
                    else:
                        new_value = new_value.replace(placeholder, "")
                
                obj[key] = new_value

    elif isinstance(obj, list):
        for item in obj:
            replace_placeholders(item, data_dict)

    return obj

def escape_xml_double(value):
    """
    Escapes special XML characters twice for nested/embedded XML.
    """
    return html.escape(html.escape(str(value), quote=True), quote=True)

def replace_placeholders_xml(xml_string: str, data_dict: dict) -> str:
    """
    Replace {placeholders} in an XML template string with values from data_dict,
    applying the correct level of XML escaping.

    Special cases
    -------------
    * workorder_details   – already raw XML; escape **once** with html.escape
    * trandate            – convert to YYYY-MM-DDThh:mm:ss if we recognise the input
    * companyname         – truncate to 25 chars, double-escape (for embedded XML)
    * all others          – double-escape via escape_xml_double
    """
    field_names = re.findall(r'\{([^}]+)\}', xml_string)
    result_xml  = xml_string

    for field_name in field_names:
        placeholder = f"{{{field_name}}}"

        # ─────────────────────────────────────────────
        # 1. workorder_details: escape ONCE, not twice
        # ─────────────────────────────────────────────
        if field_name == "workorder_details":
            if data_dict.get(field_name) is not None:
                single_escaped = html.escape(str(data_dict[field_name]), quote=True)
                result_xml = result_xml.replace(placeholder, single_escaped)
            else:
                result_xml = result_xml.replace(placeholder, "")
            continue  # next placeholder

        # ─────────────────────────────────────────────
        # 2. original logic for every other field
        # ─────────────────────────────────────────────
        if data_dict.get(field_name) is not None:

            # 🔵 trandate  ➜  ISO-8601
            if field_name == "trandate":
                value = data_dict[field_name]
                if isinstance(value, datetime.datetime):
                    formatted = value.strftime('%Y-%m-%dT%H:%M:%S')
                    result_xml = result_xml.replace(placeholder, formatted)
                elif isinstance(value, str):
                    date_formats = ['%Y-%m-%d %H:%M:%S', '%m/%d/%Y', '%Y-%m-%d']
                    date_obj = None
                    for fmt in date_formats:
                        try:
                            date_obj = datetime.datetime.strptime(value, fmt)
                            break
                        except ValueError:
                            continue
                    if date_obj:
                        formatted = date_obj.strftime('%Y-%m-%dT%H:%M:%S')
                        result_xml = result_xml.replace(placeholder, formatted)
                    else:
                        result_xml = result_xml.replace(
                            placeholder, escape_xml_double(value)
                        )
                else:
                    result_xml = result_xml.replace(
                        placeholder, escape_xml_double(value)
                    )

            # 🟡 companyname  ➜  truncate + double-escape
            elif field_name == "companyname":
                truncated = str(data_dict[field_name])[:25]
                result_xml = result_xml.replace(
                    placeholder, escape_xml_double(truncated)
                )
            elif field_name == "productionline":
                truncated = str(data_dict[field_name])[:25]
                truncated = str(data_dict[field_name]).replace('FLIGHT -', 'Flight').replace('MANUAL - ', 'MANUAL-')[:25]
                result_xml = result_xml.replace(
                    placeholder, escape_xml_double(truncated)
                )                
            elif field_name == "memo":
                truncated = str(data_dict[field_name])[:25]
                result_xml = result_xml.replace(
                    placeholder, escape_xml_double(truncated)
                )

            else:
                result_xml = result_xml.replace(
                    placeholder, escape_xml_double(data_dict[field_name])
                )
        else:
            # missing value → blank out placeholder
            result_xml = result_xml.replace(placeholder, "")

    return result_xml

def send_netsuite_request(payload, script, deployment):
    secrets = get_secrets()

    # NetSuite credentials
    ns_account_id = secrets["realmId"]
    consumer_key = secrets["nsUploadClient"]
    consumer_secret = secrets["nsUploadSecret"]
    token = secrets["nsUploadTokenId"]
    token_secret = secrets["nsUploadTokenSecret"]
    base_url = secrets["nsBaseUrl"]

    # NetSuite RESTlet URL - Fixed f-string formatting
    url = f"{base_url}?script={script}&deploy={deployment}"

    # Create OAuth1 authentication object
    auth = OAuth1(
        client_key=consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=token,
        resource_owner_secret=token_secret,
        signature_method="HMAC-SHA256",
        realm=ns_account_id
    )
    
    # Set proper headers - match exactly what works in Postman
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Convert payload to string to ensure proper formatting
    payload_json = json.dumps(payload)
    
    # Make POST request
    response = requests.post(
        url, 
        headers=headers, 
        auth=auth, 
        data=payload_json
    )

    print("Status Code:", response.status_code)
    try:
        return response.json()
    except ValueError:
        return {"error": "Invalid JSON response", "text": response.text}

def extract_parts_from_url(url):
    """Extract account name, file share name, and file path from URL"""
    parsed_url = urlparse(url)
    parts = parsed_url.path.strip('/').split('/')
    
    if len(parts) >= 1:
        account_name = parsed_url.netloc.split('.')[0]
        file_share_name = parts[0]
        file_path = '/'.join(parts[1:]) if len(parts) > 1 else ""
        
        return {
            'accountName': account_name, 
            'fileShareName': file_share_name, 
            'filePath': file_path
        }
    return None

def generate_authentication_string(verb, date, account_name, file_share_name, file_path):

    secrets = get_secrets()

    ACCOUNT_KEY = secrets["azureFileKey"]

    """Generate the Azure File Storage authentication signature"""
    canonicalized_headers = f"x-ms-date:{date}\nx-ms-version:2019-02-02"
    canonicalized_resource = f"/{account_name}/{file_share_name}/{file_path}"
    
    string_to_sign = f"{verb}\n\n\n\n\n\n\n\n\n\n\n\n{canonicalized_headers}\n{canonicalized_resource}"
    
    # Compute HMAC-SHA256 signature
    decoded_key = base64.b64decode(ACCOUNT_KEY)
    signature = base64.b64encode(hmac.new(decoded_key, string_to_sign.encode('utf-8'), hashlib.sha256).digest()).decode()
    
    return f"SharedKey {account_name}:{signature}"

def fetch_azure_file(url):
    """Fetch file from Azure File Storage"""
    parts = extract_parts_from_url(url)
    if not parts:
        raise ValueError("Invalid Azure file URL structure")
    
    account_name = parts['accountName']
    file_share_name = parts['fileShareName']
    file_path = parts['filePath']
    
    date = datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
    
    auth = generate_authentication_string("GET", date, account_name, file_share_name, file_path)
    #print(f"auth string: {auth}")

    headers = {
        "x-ms-date": date,
        "x-ms-version": "2019-02-02",
        "Authorization": auth
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.text
    else:
        raise Exception(f"Failed to fetch file: {response.status_code}, Response: {response.text}")
    
def parse_shipments_xml(xml_content):
    import xml.etree.ElementTree as ET

    # Parse XML
    root = ET.fromstring(xml_content)
    
    # Define namespace prefix for easier referencing
    namespaces = {
        'ils': 'http://www.manh.com/ILSNET/Interface'
    }
    
    # Find all shipment elements
    shipments = root.findall('.//ils:Shipment', namespaces)
    
    # Create array to hold shipment data
    shipment_data = []
    
    for shipment in shipments:
        # Skip deleted shipments
        deleted = shipment.find('ils:Deleted', namespaces)
        if deleted is not None and deleted.text == 'Y':
            continue
            
        # Extract data from each shipment
        shipment_info = {}

        # Date
        creation_date = shipment.find('ils:CreationDateTimeStamp', namespaces)
        if creation_date is not None:
            shipment_info['date'] = creation_date.text

        # InterfaceRecordId
        interface_id = shipment.find('ils:InterfaceRecordId', namespaces)
        if interface_id is not None:
            shipment_info['InterfaceRecordId'] = interface_id.text

        # BolNumAlpha
        bol_num = shipment.find('ils:BolNumAlpha', namespaces)
        if bol_num is not None:
            shipment_info['BolNumAlpha'] = bol_num.text

        # ErpOrder needs to be mapped to InternalShipmentNum
        erp_order = shipment.find('ils:ErpOrder', namespaces)
        if erp_order is not None:
            shipment_info['InternalShipmentNum'] = erp_order.text
        #seal number
        seal_number = shipment.find('ils:UserDef1', namespaces)
        if seal_number is not None:
            shipment_info['seal_number'] = seal_number.text

        #pro number
        pro_number = shipment.find('ils:UserDef2', namespaces)
        if pro_number is not None:
            shipment_info['pro_number'] = pro_number.text

        shipment_id = shipment.find('ils:ShipmentId', namespaces)
        if shipment_id is not None:
            shipment_info['ShipmentId'] = shipment_id.text

        # Create a mapping of container IDs to SKU items
        # This will help us associate the right Item with each container
        container_to_item_map = {}
        
        # Find all ShipmentDetail elements to map items to containers
        details = shipment.findall('.//ils:ShipmentDetail', namespaces)
        for detail in details:
            # Get internal line number to match with container
            line_num = detail.find('ils:InternalShipmentLineNum', namespaces)
            if line_num is None:
                continue
                
            # Get the Item/SKU for this detail
            sku = detail.find('.//ils:SKU/ils:Item', namespaces)
            if sku is None:
                continue
                
            # Store in our mapping
            container_to_item_map[line_num.text] = sku.text

        # Container info 
        containers = shipment.findall('.//ils:ShippingContainer', namespaces)
        container_list = []
        
        for container in containers:
            container_info = {}
            
            # Get ContainerId
            container_id = container.find('ils:ContainerId', namespaces)
            if container_id is not None:
                container_info['ContainerId'] = container_id.text

            # Each container has ContainerDetails which link to the items
            container_details = container.findall('.//ils:ContainerDetail', namespaces)
            for detail in container_details:
                # Get shipment line number to look up the item
                ship_line_num = detail.find('ils:InternalShipmentLineNum', namespaces)
                if ship_line_num is not None and ship_line_num.text in container_to_item_map:
                    container_info['Item'] = container_to_item_map[ship_line_num.text]
                
                # Get lot, quantity and unit
                lot = detail.find('ils:Lot', namespaces)
                qty = detail.find('ils:Quantity', namespaces)
                quantity_um = detail.find('ils:QuantityUm', namespaces)
                
                if lot is not None:
                    container_info['Lot'] = lot.text
                if qty is not None:
                    container_info['Quantity'] = qty.text
                if quantity_um is not None:
                    container_info['QuantityUM'] = quantity_um.text
            
            container_list.append(container_info)

        if container_list:
            shipment_info['Containers'] = container_list
        
        # Add shipment record
        shipment_data.append(shipment_info)
    
    # Return the result in the desired format
    return {"shipments": shipment_data}

def extract_transaction_histories(xml_content):
    import xml.etree.ElementTree as ET
    
    # Parse XML
    root = ET.fromstring(xml_content)
    
    # Define namespace
    ns_url = 'http://www.manh.com/ILSNET/Interface'
    
    # Find all transaction history elements
    transaction_histories = root.findall(f'.//{{{ns_url}}}TransactionHistory')
    
    # Initialize result
    result = {"TransactionHistories": []}
    
    # Process each transaction history
    for history in transaction_histories:
        # Extract required fields
        warehouse = history.find(f'{{{ns_url}}}Warehouse')
        item = history.find(f'{{{ns_url}}}Item')
        direction = history.find(f'{{{ns_url}}}Direction')
        quantity = history.find(f'{{{ns_url}}}Quantity')
        if quantity is not None and quantity.text:
            quantity_value = float(quantity.text) * -1 if direction is not None and direction.text == "From" else float(quantity.text)
        else:
            quantity_value = 0  # Default to 0 if quantity is missing or invalid
        quantity.text = str(quantity_value)  # Update quantity text to reflect the value
        lot = history.find(f'{{{ns_url}}}Lot')
        referenceid = history.find(f'{{{ns_url}}}ReferenceID')
        InternalID = history.find(f'{{{ns_url}}}InternalID')
        exp_date = history.find(f'{{{ns_url}}}AfterExpDate')
        if exp_date is None:
            exp_date = history.find(f'{{{ns_url}}}BeforeExpDate')
        if exp_date is not None and exp_date.text == '4712-12-31T00:00:00':
            exp_date.text = ""
        ref_type = history.find(f'{{{ns_url}}}ReferenceType')
        trans_type = history.find(f'{{{ns_url}}}TransactionType')
        quantity_um = history.find(f'{{{ns_url}}}QuantityUM')
        work_zone = history.find(f'{{{ns_url}}}WorkZone')
        after_status = history.find(f'{{{ns_url}}}AfterSts')
        before_status = history.find(f'{{{ns_url}}}BeforeSts')
        to_warehouse = history.find(f'{{{ns_url}}}ToWarehouse')
        bin = history.find(f'{{{ns_url}}}Location')
        
        # Create transaction object with safe extraction (None handling)
        transaction = {
            "Warehouse": warehouse.text if warehouse is not None else "",
            "sku": item.text if item is not None else "",
            "quantity": quantity.text if quantity is not None else "0",
            "direction": direction.text if direction is not None else "",
            "referenceid": referenceid.text if referenceid is not None else "",
            "InternalID": InternalID.text if InternalID is not None else "",
            "lot": lot.text if lot is not None else "",
            "expirationdate": exp_date.text if exp_date is not None else "",
            "ReferenceType": ref_type.text if ref_type is not None else "",
            "TransactionType": trans_type.text if trans_type is not None else "",
            "QuantityUM": quantity_um.text if quantity_um is not None else "",
            "WorkZone": work_zone.text if work_zone is not None else "",
            "AfterSts": after_status.text if after_status is not None else "",
            "BeforeSts": before_status.text if before_status is not None else "",
            "ToWarehouse": to_warehouse.text if to_warehouse is not None else "",
            "bin": bin.text if bin is not None else ""            
        }
        
        # Add to result
        result["TransactionHistories"].append(transaction)
    
    return result

def clean(part):
    return re.sub(r'[^A-Za-z0-9_-]', '', part)

def parse_inventory_balance_xml(xml_string):
    ns = {'ns': 'http://www.manh.com/ILSNET/Interface'}
    root = ET.fromstring(xml_string)
    data = []

    for inv in root.findall('.//ns:Inventory', namespaces=ns):
        sku_node = inv.find('ns:SKU', namespaces=ns)

        item_code = sku_node.findtext('ns:Item', default='', namespaces=ns)
        item_code = item_code  # Clean item code
        lot_number = sku_node.findtext('ns:Lot', default='', namespaces=ns)
        expiration = inv.findtext('ns:ExpirationDate', default='', namespaces=ns)
        status = inv.findtext('ns:Status', default='', namespaces=ns)
        quantity = sku_node.findtext('ns:Quantity', default='0', namespaces=ns)
        location = inv.findtext('ns:Warehouse', default='', namespaces=ns).upper()
        external_id = inv.findtext('ns:InternalID', default='', namespaces=ns)

        # Convert expiration date if needed
        if expiration:
            try:
                expiration = datetime.datetime.strptime(expiration, "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d")
            except ValueError:
                expiration = None



        entry = {
            "externalId": external_id,
            "item": item_code,
            "lot": lot_number,
            "expirationDate": expiration,
            "status": status,
            "quantity": float(quantity),
            "location": location
        }

        data.append(entry)

    return { "data": data }

def parse_adjustment_xml(xml_content):
    import xml.etree.ElementTree as ET

    # Parse XML
    root = ET.fromstring(xml_content)

    # Define namespace (default, no prefix used in this XML)
    ns_url = 'http://www.manh.com/ILSNET/Interface'
    ns = {'': ns_url}
    ET.register_namespace('', ns_url)

    # Find all transaction history elements
    transaction_histories = root.findall(f'.//{{{ns_url}}}TransactionHistory')

    # Initialize result
    adjustment_payload = {
        "location": None,
        "memo": "",
        "ReferenceID": None,
        "ReferenceType": None,
        "items": []
    }

    # Prepare item groupings
    items_by_key = {}

    for i, history in enumerate(transaction_histories):
        item_id = history.find(f'{{{ns_url}}}Item')
        item_sku = history.find(f'{{{ns_url}}}Item')
        lot = history.find(f'{{{ns_url}}}Lot')
        lot = lot.text.replace('  ', '').replace('\r', '') if lot is not None else None
        qty = history.find(f'{{{ns_url}}}Quantity')
        status = history.find(f'{{{ns_url}}}AfterSts')
        location = history.find(f'{{{ns_url}}}Warehouse')
        shipment_ref = history.find(f'{{{ns_url}}}ReferenceID')
        shipment_type = history.find(f'{{{ns_url}}}ReferenceType')

        # Set location once (same for all lines)
        if adjustment_payload["location"] is None and location is not None:
            adjustment_payload["location"] = location.text

        # Set ReferenceID and ReferenceType only from the first transaction
        if i == 0:
            if shipment_ref is not None:
                adjustment_payload["ReferenceID"] = shipment_ref.text
            if shipment_type is not None:
                adjustment_payload["ReferenceType"] = shipment_type.text

        # Create memo using item and ref
        if shipment_ref is not None and item_sku is not None:
            adjustment_payload["memo"] = f"Auto-adjustment for item {item_sku.text} (shipment {shipment_ref.text})"

        # Group items by item_id for batching
        key = item_id.text if item_id is not None else item_sku.text
        if key not in items_by_key:
            items_by_key[key] = {
                "item": item_id.text if item_id is not None else item_sku.text,
                "quantity": 0,
                "location": location.text if location is not None else "",
                "inventorydetail": []
            }

        # Add inventory detail
        detail = {
            "inventorynumber": lot.text if lot is not None else "",
            "status": 1 if (status is not None and status.text == 'Unrestricted') else 2,
            "quantity": float(qty.text) if qty is not None else 0
        }

        items_by_key[key]["inventorydetail"].append(detail)
        items_by_key[key]["quantity"] += detail["quantity"]

    # Finalize items list
    adjustment_payload["items"] = list(items_by_key.values())

    return adjustment_payload

def parse_receipts_xml(xml_content):
    """
    Parses receipt XML and groups data by ErpOrderNum.
    Ensures each ReceiptContainer is included only once per group.
    """
    root = ET.fromstring(xml_content)
    ns = {'manh': 'http://www.manh.com/ILSNET/Interface'}

    grouped = defaultdict(lambda: {"date": None, "ReceiptId": None, "containers": [], "seen": set()})

    for receipt in root.findall('.//manh:Receipt', ns):
        date = receipt.findtext('manh:CreationDateTimeStamp', default=None, namespaces=ns)
        receipt_id = receipt.findtext('manh:ReceiptId', default=None, namespaces=ns)

        for container in receipt.findall('.//manh:ReceiptContainer', ns):
            cont_detail = container.find('manh:ReceiptDetail', ns)
            if cont_detail is None:
                continue
            erp_order = cont_detail.findtext('manh:ErpOrderNum', default=None, namespaces=ns)
            if not erp_order:
                continue

            entry = grouped[erp_order]
            # Set metadata once
            if entry["date"] is None:
                entry["date"] = date
            if entry["ReceiptId"] is None:
                entry["ReceiptId"] = receipt_id

            cid = container.findtext('manh:ContainerId', default=None, namespaces=ns)
            # Avoid duplicates
            if cid in entry["seen"]:
                continue
            entry["seen"].add(cid)

            sku = cont_detail.findtext('manh:SKU/manh:Item', default=None, namespaces=ns)
            container_info = {
                "ContainerId": cid,
                "Lot": container.findtext('manh:Lot', default=None, namespaces=ns),
                "Quantity": container.findtext('manh:Qty', default=None, namespaces=ns),
                "ExpirationDate": container.findtext('manh:ExpDate', default=None, namespaces=ns),
                "SKU": sku
            }
            entry["containers"].append(container_info)

    response = {
        "receipts": [
            {
                "ErpOrderNum": erp,
                "date": info["date"],
                "ReceiptId": info["ReceiptId"],
                "containers": info["containers"]
            }
            for erp, info in grouped.items()
        ]
    }

    return response

def format_date(date_str):
    """Format date from MM/DD/YYYY to YYYYMMDD"""
    try:
        # Parse the date string
        date_obj = datetime.datetime.strptime(date_str, "%m/%d/%Y")
        # Format to YYYYMMDD
        return date_obj.strftime("%Y%m%d")
    except:
        # Return current date if there's an error
        return datetime.datetime.now().strftime("%Y%m%d")

def get_uploaded_interface_file_by_key(key):
    # Load secrets from JSON file
    secrets = get_secrets()

    # Get Scale Token
    token = getScaleBearerToken()
    if not token:
        raise ValueError("Failed to retrieve access token.")

    # Build URL
    url = f"https://{secrets['scaleURL']}/general/scaleapi/InterfaceUploadApi/uploaded-InterfaceFiles?key={key}"

    # Set headers
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Environment": secrets["Environment"],
        "Warehouse": secrets["Warehouse"]
    }

    # Make GET request
    response = requests.get(url, headers=headers)

    # Try parsing the response
    try:
        data = response.json()
    except json.JSONDecodeError:
        return []  # Malformed response or not JSON

    # Check for presence of FileLinks
    if isinstance(data, dict) and "FileLinks" in data and isinstance(data["FileLinks"], list):
        return data["FileLinks"]
    else:
        return []  # No files available or error message response

def generate_detail_block(components):
    details_xml = ""
    for index, comp in enumerate(components, start=1):
        detail_xml = f"""
                &lt;BillOfMaterialDetail&gt;
                    &lt;AllocationRule&gt;Work Order Allocation&lt;/AllocationRule&gt;
                    &lt;BuildLevel&gt;1&lt;/BuildLevel&gt;
                    &lt;BuildSequence&gt;{escape_xml_double(index)}&lt;/BuildSequence&gt;
                    &lt;Company&gt;{escape_xml_double(comp['companyname'])}&lt;/Company&gt;
                    &lt;InterfaceEntity&gt;
                        &lt;Action&gt;Save&lt;/Action&gt;
                    &lt;/InterfaceEntity&gt;
                    &lt;Item&gt;{escape_xml_double(comp['component'])}&lt;/Item&gt;
                    &lt;QtyNeededPerItem&gt;{escape_xml_double(comp['quantity'])}&lt;/QtyNeededPerItem&gt;
                    &lt;QtyUm&gt;{escape_xml_double(comp['uom'])}&lt;/QtyUm&gt;
                &lt;/BillOfMaterialDetail&gt;"""
        details_xml += detail_xml
    return f"&lt;BillOfMaterialDetails&gt;{details_xml}\n\t\t&lt;/BillOfMaterialDetails&gt;"

def format_qty(qty: str | float | int, precision: int = 5) -> str:
    """
    Convert any numeric input to a trimmed string with the desired precision.
    """
    dec = Decimal(str(qty)).quantize(Decimal(f"1.{'0'*precision}"), rounding=ROUND_HALF_UP)
    return format(dec.normalize(), "f")

def generate_workorder_detail_block(components, *, qty_precision=5):
    details_xml = ""
    workOrderQty = 0

    # Calculate total quantity for mainline items
    for comp in components:
        if comp['mainline'] == 'T':
            workOrderQty += abs(float(comp['quantity']))

    # Generate formatted XML for each component
    sequence = 0
    for comp in components:
        if comp['mainline'] == 'F':
            sequence += 1
            qty_needed_per_item = float(comp['quantity']) / workOrderQty

            # Double-escape company name safely
            company_escaped = html.escape(str(comp['companyname']), quote=True)
            ##get the first 25 characters
            company_escaped = company_escaped[:25]

            details_xml += (
                "      <WorkOrderDetail>\n"
                "        <AllocationRule>Work Order Allocation</AllocationRule>\n"
                f"        <BuildSequence>{sequence}</BuildSequence>\n"
                f"        <Company>{company_escaped}</Company>\n"
                f"        <ComponentItem>{comp['itemid']}</ComponentItem>\n"
                "        <InterfaceEntity>\n"
                "          <Action>SAVE</Action>\n"
                "        </InterfaceEntity>\n"
                f"        <QtyNeededPerItem>{qty_needed_per_item:.5f}</QtyNeededPerItem>\n"
                f"        <QuantityUm>{comp['unit']}</QuantityUm>\n"
                "      </WorkOrderDetail>\n"
            )

    return details_xml                    

def send_bom_for_order(order_id):
    # Load queries
    queries = get_queries()  # <-- This line fixes it

    # Load XML template
    payload_template = load_xml_template("templateBom.xml")


    # Format query with order ID
    sql_query = queries["get_bom_for_wo"].format(orderId=order_id)
    netsuite_response = query_netsuite(sql_query, 100, 0)
    #print(f"NetSuite BOM Query Result for order {order_id}:\n", netsuite_response)

    # Group components by itemid
    grouped_items = defaultdict(list)
    for item in netsuite_response.get("items", []):
        grouped_items[item["itemid"]].append(item)

    for itemid, components in grouped_items.items():
        base_item = components[0]
        item_payload = payload_template

        # Generate the detail block
        detail_block = generate_detail_block(components)
        item_payload = item_payload.replace("{BillOfMaterialDetails}", detail_block)

        # Fill in remaining placeholders
        item_payload = replace_placeholders_xml(item_payload, base_item)
        print(f"Final XML Payload for item {itemid}:\n", item_payload)

        # Post the payload
        response = post_to_scale_api("billOfMaterials-Downloaded", item_payload, content_type="xml")
        print(f"Response BOM item {itemid}:\n", response)
        return response

def log_error(file_name, message):
    """
    Appends an error message to the specified log file using UTF-8 encoding.
    
    Args:
        file_name (str): Name of the log file (with .txt extension)
        message (str): Error message to append to the log file
    """
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(file_name, 'a', encoding='utf-8') as log_file:
            log_file.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        print(f"Error writing to log file {file_name}: {str(e)}")

def was_processed(item_id, filename):
    """
    Check if the item_id was already processed and recorded in the given JSON file.
    """
    try:
        if not os.path.exists(filename):
            return False
        with open(filename, 'r') as f:
            processed = json.load(f)
        return str(item_id) in processed
    except Exception as e:
        print(f"Error checking processed file: {e}")
        return False

def mark_as_processed(item_id, filename):
    """
    Add an item_id to the JSON file to mark it as processed.
    Creates the file if it doesn't exist.
    """
    try:
        processed = []
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                processed = json.load(f)

        if str(item_id) not in processed:
            processed.append(str(item_id))
            with open(filename, 'w') as f:
                json.dump(processed, f, indent=2)
    except Exception as e:
        print(f"Error updating processed file: {e}")


def post_to_scale_generic_api(payload):
    # Load secrets from JSON file
    secrets = get_secrets()
    base_url = f"https://{secrets['scaleURL']}/general/scaleapi/GenericDataBindApi"
    print(f"Posting to Scale Generic API at {base_url}")


    token = getScaleBearerToken()
    if not token:
        raise ValueError("Failed to retrieve access token.")

    # Set request headers dynamically based on content type
    headers = {
        "Authorization": f"Bearer {token}",
        "environment": secrets["Environment"],
        "warehouse": secrets["Warehouse"],
        "Accept": "application/json"
    }

    headers["Content-Type"] = "application/json"
    if isinstance(payload, (list, dict)):
        payload = json.dumps(payload)  # Convert dict to JSON string


    # Send the request
    response = requests.post(base_url, headers=headers, data=payload)
    print(f"response: {response}")

    # Handle response
    if response.status_code == 200:
        try:
            return response.status_code, response.json()  # Return JSON response
        except json.JSONDecodeError:
            return response.status_code, response.text  # Return raw text if not valid JSON

    else:
        return response.status_code, response.text

def load_or_create_json_file(filename, default_content=None):
    secrets = get_secrets()
    hostname = secrets["sojohostname"]
    username = secrets["sojousername"]
    password = secrets["sojopassword"]
    realm = secrets["realmId"]
    filename = filename.replace('.json', f"_{realm}.json")
    port = 22
    
    if default_content is None:
        default_content = {}

    try:
        # Connect to SFTP
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(hostname=hostname, username=username, password=password, port=port)
        sftp_client = ssh_client.open_sftp()

        # Try to read the file
        try:
            with sftp_client.file(filename, mode='r') as f:
                print(f"Loading existing file: {filename}")
                file_content = f.read().decode("utf-8")
                json_data = json.loads(file_content)
        except FileNotFoundError:
            print(f"{filename} not found. Creating with default content...")
            json_bytes = json.dumps(default_content, indent=2).encode("utf-8")
            file_obj = io.BytesIO(json_bytes)
            sftp_client.putfo(file_obj, filename)
            json_data = default_content

        # Cleanup
        sftp_client.close()
        ssh_client.close()
        return json_data

    except Exception as e:
        print(f"Error loading or creating JSON file: {e}")
        return None

def save_json_file(filename, content):
    secrets = get_secrets()
    hostname = secrets["sojohostname"]
    username = secrets["sojousername"]
    password = secrets["sojopassword"]
    realm = secrets["realmId"]
    filename = filename.replace('.json', f"_{realm}.json")
    port = 22

    try:
        # Establish SSH/SFTP connection
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(hostname=hostname, username=username, password=password, port=port)
        sftp_client = ssh_client.open_sftp()

        # Prepare the JSON content as bytes
        json_bytes = json.dumps(content, indent=2).encode("utf-8")
        file_obj = io.BytesIO(json_bytes)

        # Upload the file
        sftp_client.putfo(file_obj, filename)
        print(f"Successfully saved {filename} to SFTP.")

        # Close connections
        sftp_client.close()
        ssh_client.close()
        return True

    except Exception as e:
        print(f"Failed to save JSON file {filename}: {e}")
        return False
    

def _sftp_mkdir_p(sftp_client, remote_dir: str):
    """
    Recursively create remote_dir on the SFTP server if it doesn't exist.
    Works like `mkdir -p`.
    """
    # Normalize and split into parts (POSIX-style paths)
    parts = PurePosixPath(remote_dir).parts
    if not parts:
        return
    path_accum = ""
    for part in parts:
        path_accum = f"{path_accum}/{part}" if path_accum else part
        try:
            sftp_client.stat(path_accum)
        except FileNotFoundError:
            sftp_client.mkdir(path_accum)

def save_payload_to_sftp(filename: str, data, *, ensure_ascii: bool = False, indent: int = 2):
    secrets = get_secrets()
    hostname = secrets["sojohostname"]
    username = secrets["sojousername"]
    password = secrets["sojopassword"]
    realm = secrets["realmId"]
    port = 22

    # Build timestamped filename
    # Example: filename='order_payload.json' -> 'order_payload_20250906T141500Z.json'
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # Split extension (simple dot split)
    if "." in filename:
        base, ext = filename.rsplit(".", 1)
        ext = "." + ext
    else:
        base, ext = filename, ".json"
    stamped_filename = f"{base}_{ts}{ext}"

    # Remote dir is the realm; remote path = "<realm>/<stamped_filename>"
    remote_dir = realm
    remote_path = f"{remote_dir}/{stamped_filename}"

    ssh_client = None
    sftp_client = None

    try:
        # Connect
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(hostname=hostname, username=username, password=password, port=port)
        sftp_client = ssh_client.open_sftp()

        # Ensure realm directory exists
        _sftp_mkdir_p(sftp_client, remote_dir)

        # Serialize JSON and upload
        json_bytes = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii).encode("utf-8")
        with io.BytesIO(json_bytes) as buf:
            sftp_client.putfo(buf, remote_path)

        print(f"Saved payload to SFTP: {remote_path}")
        return remote_path

    except Exception as e:
        print(f"Failed to save payload to SFTP: {e}")
        return None

    finally:
        try:
            if sftp_client:
                sftp_client.close()
        finally:
            if ssh_client:
                ssh_client.close()
