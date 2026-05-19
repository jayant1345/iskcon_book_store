# -*- coding: utf-8 -*-
"""Try multiple Delhivery API endpoints to find registered warehouse/pickup names."""
import os, json, requests
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.environ.get("DELHIVERY_API_TOKEN", "")
HEADERS = {"Authorization": "Token " + TOKEN}
BASE = "https://track.delhivery.com"

endpoints = [
    "/api/backend/clientwarehouse/get/",
    "/api/p/pudo/",
    "/api/backend/clientwarehouse/get/?format=json",
    "/api/v3/manifest/",
    "/fm/request/new/",
    "/api/cmu/pickup/?format=json",
]

for ep in endpoints:
    url = BASE + ep
    print("\n--- GET " + url + " ---")
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        print("HTTP:", r.status_code)
        ct = r.headers.get("Content-Type", "")
        if "json" in ct:
            data = r.json()
            print(json.dumps(data, indent=2)[:2000])
        else:
            # look for pickup/warehouse names in raw HTML
            text = r.text
            for keyword in ["Warehouse", "warehouse", "Pickup", "pickup", "Iskcon", "ISKCON", "Thaltej", "Mandir"]:
                idx = text.lower().find(keyword.lower())
                if idx != -1:
                    print("Found keyword '" + keyword + "' at position " + str(idx))
                    print("  Context: " + text[max(0,idx-30):idx+80])
    except Exception as e:
        print("Error:", e)

# Also try a POST to the create endpoint with a deliberately wrong name
# to see if the error message hints at the correct name
print("\n\n--- Trying name variations on PRODUCTION create endpoint ---")
PROD_CREATE = BASE + "/api/cmu/create.json"

test_names = [
    "Primary",
    "ISKCON",
    "Iskcon Mandir",
    "ISKCON Mandir",
    "Iskcon Mandir, Thaltej, Ahmedabad",
    "Iskcon Mandir , Thaltej , Ahmedabad 380059",
    "ISKCON Mandir , Thaltej , Ahmedabad 380059",
    "Thaltej",
]

base_payload = {
    "shipments": [{
        "name": "Test", "add": "Test", "pin": "400053", "city": "Mumbai",
        "state": "Maharashtra", "country": "India", "phone": "9999999999",
        "order": "TEST001", "payment_mode": "Prepaid", "cod_amount": 0,
        "total_amount": 1, "products_desc": "Test", "hsn_code": "4901",
        "quantity": 1, "weight": 0.5, "shipping_mode": "Surface",
        "seller_name": "ISKCON", "seller_add": "Thaltej Ahmedabad",
        "return_pin": "380059", "return_city": "Ahmedabad",
        "return_state": "Gujarat", "return_country": "India",
        "return_phone": "9726122046", "return_add": "Iskcon Mandir Thaltej",
    }],
    "pickup_location": {"name": ""}
}

for name in test_names:
    base_payload["pickup_location"]["name"] = name
    base_payload["shipments"][0]["order"] = "TEST_" + name[:10].replace(" ", "")
    form = {"format": "json", "data": json.dumps(base_payload)}
    try:
        r = requests.post(PROD_CREATE, data=form, headers=HEADERS, timeout=10)
        data = r.json()
        rmk = data.get("rmk", "")
        success = data.get("success", False)
        pkgs = data.get("packages", [])
        waybill = pkgs[0].get("waybill", "") if pkgs else ""
        status = "[SUCCESS waybill=" + waybill + "]" if success else "[FAIL: " + rmk[:80] + "]"
        print("  Name: '" + name + "' --> " + status)
    except Exception as e:
        print("  Name: '" + name + "' --> Error: " + str(e))
