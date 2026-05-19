# -*- coding: utf-8 -*-
"""
Delhivery API Test Suite
Run: python test_delhivery.py

Tests (in order):
  1. Serviceability check -- Mumbai pincode (known serviceable)
  2. Serviceability check -- ISKCON center pincode (return address)
  3. Serviceability check -- New Delhi pincode
  4. Create dummy shipment on STAGING (no real pickup scheduled)
  5. Track shipment (if waybill returned)
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()

# -- Config -------------------------------------------------------------------

TOKEN    = os.environ.get("DELHIVERY_API_TOKEN", "")
PROD_URL = "https://track.delhivery.com"
STG_URL  = "https://staging-express.delhivery.com"

PICKUP_LOCATION = os.environ.get("DELHIVERY_PICKUP_LOCATION", "Primary")
RETURN_NAME     = os.environ.get("DELHIVERY_RETURN_NAME", "ISKCON Book Store")
RETURN_ADDRESS  = os.environ.get("DELHIVERY_RETURN_ADDRESS", "ISKCON Temple, SG Highway, Ahmedabad")
RETURN_CITY     = os.environ.get("DELHIVERY_RETURN_CITY", "Ahmedabad")
RETURN_STATE    = os.environ.get("DELHIVERY_RETURN_STATE", "Gujarat")
RETURN_PINCODE  = os.environ.get("DELHIVERY_RETURN_PINCODE", "380059")
RETURN_PHONE    = os.environ.get("DELHIVERY_RETURN_PHONE", "")

AUTH_HEADER = {"Authorization": "Token " + TOKEN}

# -- Helpers ------------------------------------------------------------------

def sep(title):
    print("\n" + "-" * 60)
    print("  " + title)
    print("-" * 60)

def ok(msg):   print("  [OK]   " + str(msg))
def fail(msg): print("  [FAIL] " + str(msg))
def info(msg): print("  [INFO] " + str(msg))

# -- Test: Serviceability -----------------------------------------------------

def test_serviceability(pincode, label=""):
    sep("Serviceability: " + (label or pincode))
    url = PROD_URL + "/c/api/pin-codes/json/?filter_codes=" + pincode
    try:
        r = requests.get(url, headers=AUTH_HEADER, timeout=10)
        info("HTTP " + str(r.status_code))

        if r.status_code == 401:
            fail("Authentication failed -- check your API token")
            return

        data = r.json()
        codes = data.get("delivery_codes", [])

        if not codes:
            fail("Pincode " + pincode + " not found or not serviceable by Delhivery")
            return

        pc = codes[0].get("postal_code", {})
        ok("Pincode    : " + str(pc.get("pin", pincode)))
        ok("City       : " + str(pc.get("city", "N/A")))
        ok("State      : " + str(pc.get("state_code", "N/A")))
        ok("COD        : " + ("Yes" if pc.get("cod") == "Y" else "No"))
        ok("Pre-paid   : " + ("Yes" if pc.get("pre_paid") == "Y" else "No"))
        ok("Pickup     : " + ("Yes" if pc.get("pickup") == "Y" else "No"))
        ok("ODA zone   : " + ("Yes (extra charges)" if pc.get("is_oda") == "Y" else "No"))

    except Exception as e:
        fail("Exception: " + str(e))


# -- Test: Create Shipment on STAGING -----------------------------------------

def test_create_staging():
    sep("Create Shipment -- STAGING (safe, no real pickup)")
    url = STG_URL + "/api/cmu/create.json"

    payload = {
        "shipments": [{
            "name": "Test Customer",
            "add": "123 Test Street, Andheri West",
            "pin": "400053",
            "city": "Mumbai",
            "state": "Maharashtra",
            "country": "India",
            "phone": "9999999999",
            "order": "TEST_ISKCON_20260519",
            "payment_mode": "COD",
            "cod_amount": 350,
            "total_amount": 350,
            "products_desc": "ISKCON Books",
            "hsn_code": "4901",
            "quantity": 1,
            "weight": 0.5,
            "shipping_mode": "Surface",
            "seller_name": RETURN_NAME,
            "seller_add": RETURN_ADDRESS,
            "return_pin": RETURN_PINCODE,
            "return_city": RETURN_CITY,
            "return_state": RETURN_STATE,
            "return_country": "India",
            "return_phone": RETURN_PHONE,
            "return_add": RETURN_ADDRESS,
        }],
        "pickup_location": {"name": PICKUP_LOCATION}
    }

    form_data = {"format": "json", "data": json.dumps(payload)}

    info("URL           : " + url)
    info("Pickup loc    : " + PICKUP_LOCATION)

    try:
        r = requests.post(url, data=form_data, headers=AUTH_HEADER, timeout=15)
        info("HTTP " + str(r.status_code))

        try:
            data = r.json()
        except Exception:
            info("Raw response  : " + r.text[:500])
            return None

        print("\n  Full JSON response:")
        print(json.dumps(data, indent=4))

        if r.status_code == 401:
            fail("Auth failed on staging -- production token may not work on staging env")
            info("This is normal. Try production dry-run below.")
            return None

        pkgs = data.get("packages", [])
        if pkgs and pkgs[0].get("waybill"):
            waybill = pkgs[0]["waybill"]
            ok("Waybill    : " + waybill)
            ok("Status     : " + str(pkgs[0].get("status")))
            return waybill
        else:
            fail("No waybill in response -- see JSON above for error details")
            return None

    except Exception as e:
        fail("Exception: " + str(e))
        return None


# -- Test: Create Shipment on PRODUCTION (dry-run) ----------------------------

def test_create_prod():
    sep("Create Shipment -- PRODUCTION dry-run (realistic data)")
    info("This creates a real waybill on your live account.")
    info("You can cancel it from the Delhivery dashboard after the test.")
    url = PROD_URL + "/api/cmu/create.json"

    payload = {
        "shipments": [{
            "name": "Ramesh Patel",
            "add": "45 Walkeshwar Road, Malabar Hill",
            "pin": "400006",
            "city": "Mumbai",
            "state": "Maharashtra",
            "country": "India",
            "phone": "9824567890",
            "order": "DRYRUN_ISKCON_20260519",
            "payment_mode": "COD",
            "cod_amount": 280,
            "total_amount": 280,
            "products_desc": "Bhagavad Gita As It Is",
            "hsn_code": "4901",
            "quantity": 1,
            "weight": 0.5,
            "shipping_mode": "Surface",
            "seller_name": RETURN_NAME,
            "seller_add": RETURN_ADDRESS,
            "return_pin": RETURN_PINCODE,
            "return_city": RETURN_CITY,
            "return_state": RETURN_STATE,
            "return_country": "India",
            "return_phone": RETURN_PHONE,
            "return_add": RETURN_ADDRESS,
        }],
        "pickup_location": {"name": PICKUP_LOCATION}
    }

    form_data = {"format": "json", "data": json.dumps(payload)}

    try:
        r = requests.post(url, data=form_data, headers=AUTH_HEADER, timeout=15)
        info("HTTP " + str(r.status_code))

        try:
            data = r.json()
        except Exception:
            info("Raw response: " + r.text[:500])
            return None

        print("\n  Full JSON response:")
        print(json.dumps(data, indent=4))

        pkgs = data.get("packages", [])
        if pkgs and pkgs[0].get("waybill"):
            waybill = pkgs[0]["waybill"]
            ok("Waybill    : " + waybill)
            ok("Status     : " + str(pkgs[0].get("status")))
            info("ACTION: Cancel waybill " + waybill + " from Delhivery dashboard if test was successful.")
            return waybill
        else:
            fail("Shipment creation failed -- see JSON above")
            return None

    except Exception as e:
        fail("Exception: " + str(e))
        return None


# -- Test: Track Shipment -----------------------------------------------------

def test_track(waybill):
    if not waybill:
        info("Skipping track test -- no waybill available")
        return
    sep("Track Shipment: " + waybill)
    url = PROD_URL + "/api/v1/packages/json/?waybill=" + waybill + "&verbose=1"
    try:
        r = requests.get(url, headers=AUTH_HEADER, timeout=10)
        info("HTTP " + str(r.status_code))
        data = r.json()
        shipment_data = data.get("ShipmentData", [{}])[0].get("Shipment", {})
        status = shipment_data.get("Status", {})
        scans  = shipment_data.get("Scans", [])
        ok("Status     : " + str(status.get("Status", "N/A")))
        ok("Info       : " + str(status.get("Instructions", "N/A")))
        ok("Scans      : " + str(len(scans)))
        if scans:
            last = scans[-1].get("ScanDetail", {})
            ok("Last scan  : " + str(last.get("Scan", "N/A")) + " @ " + str(last.get("ScanDateTime", "N/A")))
    except Exception as e:
        fail("Exception: " + str(e))


# -- Main ---------------------------------------------------------------------

if __name__ == "__main__":
    print("")
    print("=" * 60)
    print("  DELHIVERY API TEST SUITE -- ISKCON Book Store")
    print("=" * 60)

    if not TOKEN:
        print("[FAIL] DELHIVERY_API_TOKEN not set in .env -- aborting.")
        sys.exit(1)

    print("  Token   : " + TOKEN[:8] + "..." + TOKEN[-4:])
    print("  Pickup  : " + PICKUP_LOCATION)
    print("  Return  : " + RETURN_CITY + ", " + RETURN_STATE + " - " + RETURN_PINCODE)

    # Read-only serviceability checks (always safe, hit production)
    test_serviceability("400001", "Mumbai Central -- known serviceable")
    test_serviceability("380059", "ISKCON Ahmedabad -- return address pincode")
    test_serviceability("110001", "New Delhi")

    # Try staging first (no side effects even if it fails)
    waybill = test_create_staging()

    # If staging fails (token mismatch), offer production dry-run
    if not waybill:
        print("\n  Staging test could not create waybill.")
        print("  Try production dry-run? (creates a real but cancellable waybill)")
        try:
            answer = input("  Proceed? [y/N]: ").strip().lower()
        except EOFError:
            answer = "n"

        if answer == "y":
            waybill = test_create_prod()
            test_track(waybill)
    else:
        test_track(waybill)

    print("")
    print("=" * 60)
    print("  TESTS COMPLETE")
    print("=" * 60)
    print("")
