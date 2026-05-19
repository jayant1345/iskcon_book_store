# -*- coding: utf-8 -*-
"""
Test Delhivery rate calculation API.
Origin: ISKCON Ahmedabad 380054
Destination: various pincodes
"""
import os, json, requests
from dotenv import load_dotenv
load_dotenv()

TOKEN       = os.environ.get("DELHIVERY_API_TOKEN", "")
ORIGIN_PIN  = os.environ.get("DELHIVERY_RETURN_PINCODE", "380054")
BASE        = "https://track.delhivery.com"
HEADERS     = {"Authorization": "Token " + TOKEN}

def get_rate(dest_pin, weight_grams=500, mode="S"):
    """
    md  = S (Surface) / E (Express)
    cgm = weight in grams
    pt  = Pre-paid
    cod = 0
    """
    url = (
        BASE + "/api/kinko/v1/invoice/charges/.json"
        "?md=" + mode +
        "&ss=Delivered"
        "&d_pin=" + dest_pin +
        "&o_pin=" + ORIGIN_PIN +
        "&cgm=" + str(weight_grams) +
        "&pt=Pre-paid"
        "&cod=0"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        print("  HTTP " + str(r.status_code) + "  dest=" + dest_pin + "  weight=" + str(weight_grams) + "g")
        data = r.json()
        print("  " + json.dumps(data, indent=2)[:600])

        # Try to extract the charge
        if isinstance(data, list) and data:
            charge_data = data[0]
            total = charge_data.get("total_amount") or charge_data.get("freight_charge")
            print("  --> Shipping charge: Rs." + str(total))
            return total
        elif isinstance(data, dict):
            total = data.get("total_amount") or data.get("freight_charge") or data.get("charge")
            print("  --> Shipping charge: Rs." + str(total))
            return total
    except Exception as e:
        print("  Error: " + str(e))
    return None

print("=" * 60)
print("  DELHIVERY RATE API TEST")
print("  Origin PIN: " + ORIGIN_PIN)
print("=" * 60)

test_cases = [
    ("400001", 500,  "Mumbai   500g  Surface"),
    ("400001", 1000, "Mumbai  1000g  Surface"),
    ("110001", 500,  "Delhi    500g  Surface"),
    ("560001", 500,  "Bangalore 500g Surface"),
    ("700001", 500,  "Kolkata  500g  Surface"),
    ("380001", 500,  "Ahmedabad 500g Surface"),
]

for dest_pin, grams, label in test_cases:
    print("\n--- " + label + " ---")
    get_rate(dest_pin, grams)

print("\n" + "=" * 60)
print("  DONE")
print("=" * 60)
