"""
Delhivery B2C API helper module.
All configuration is read from environment variables (loaded via .env).
"""
import os
import json
import requests

_BASE        = "https://track.delhivery.com"
_ORIGIN_PIN  = os.environ.get("DELHIVERY_RETURN_PINCODE", "380054")
_TOKEN       = os.environ.get("DELHIVERY_API_TOKEN", "")
_WEIGHT_KG   = float(os.environ.get("DELHIVERY_DEFAULT_WEIGHT", "0.1"))
_SHIP_MODE   = os.environ.get("DELHIVERY_SHIPPING_MODE", "Surface")
_PICKUP_LOC  = os.environ.get("DELHIVERY_PICKUP_LOCATION", "bhavesh")
_RETURN_NAME = os.environ.get("DELHIVERY_RETURN_NAME", "ISKCON Book Store")
_RETURN_ADDR = os.environ.get("DELHIVERY_RETURN_ADDRESS", "")
_RETURN_CITY = os.environ.get("DELHIVERY_RETURN_CITY", "Ahmedabad")
_RETURN_STATE= os.environ.get("DELHIVERY_RETURN_STATE", "Gujarat")
_RETURN_PHONE= os.environ.get("DELHIVERY_RETURN_PHONE", "")

_TIMEOUT = 10


def _auth():
    return {"Authorization": "Token " + _TOKEN}


def _mode():
    return "E" if _SHIP_MODE.strip().lower() == "express" else "S"


# ── Public API ────────────────────────────────────────────────────────────────

def check_serviceability(pincode):
    """
    Check if Delhivery delivers to a pincode.
    Returns dict: {serviceable, pre_paid, city, state, oda, error?}
    """
    url = _BASE + "/c/api/pin-codes/json/?filter_codes=" + str(pincode)
    try:
        r = requests.get(url, headers=_auth(), timeout=_TIMEOUT)
        codes = r.json().get("delivery_codes", [])
        if not codes:
            return {"serviceable": False, "error": "Pincode not serviceable"}
        pc = codes[0].get("postal_code", {})
        return {
            "serviceable": True,
            "pre_paid":    pc.get("pre_paid") == "Y",
            "city":        pc.get("city", ""),
            "state":       pc.get("state_code", ""),
            "oda":         pc.get("is_oda") == "Y",
        }
    except Exception as e:
        return {"serviceable": False, "error": str(e)}


def get_shipping_rate(dest_pin, weight_grams=None):
    """
    Get Prepaid shipping rate from ISKCON centre to dest_pin.
    Returns (rate_float, zone_str, error_str).
    rate_float is None on failure.
    """
    if weight_grams is None:
        weight_grams = int(_WEIGHT_KG * 1000)

    url = (
        _BASE + "/api/kinko/v1/invoice/charges/.json"
        "?md=" + _mode() +
        "&ss=Delivered"
        "&d_pin=" + str(dest_pin) +
        "&o_pin=" + _ORIGIN_PIN +
        "&cgm=" + str(int(weight_grams)) +
        "&pt=Pre-paid"
        "&cod=0"
    )
    try:
        r = requests.get(url, headers=_auth(), timeout=_TIMEOUT)
        data = r.json()
        if isinstance(data, list) and data:
            row = data[0]
            total = row.get("total_amount")
            if total is not None:
                return round(float(total), 2), row.get("zone", ""), None
        return None, "", "Rate unavailable for this pincode"
    except Exception as e:
        return None, "", str(e)


# Delhivery's published Surface-mode TAT (business days) by rate zone.
_ZONE_TAT   = {
    "A": (1, 2),
    "B": (2, 3),
    "C": (3, 4),
    "D": (4, 5),
    "E": (5, 7),
}
_DEFAULT_TAT = (3, 6)
_ODA_EXTRA_DAYS = 2


def estimate_delivery_days(zone, oda=False):
    """
    Estimate Surface delivery TAT (business days) from the rate zone
    returned by get_shipping_rate(). Returns (min_days, max_days).
    """
    low, high = _ZONE_TAT.get((zone or "").strip().upper(), _DEFAULT_TAT)
    if oda:
        low, high = low + _ODA_EXTRA_DAYS, high + _ODA_EXTRA_DAYS
    return low, high


def create_shipment(order):
    """
    Book a Prepaid Delhivery shipment for an Order object.
    Returns (waybill_str, error_str).  waybill is None on failure.
    """
    total_qty = sum(item.quantity for item in order.items)
    weight_kg = max(
        sum(item.quantity * (item.book.weight_kg if item.book and item.book.weight_kg is not None and item.book.weight_kg > 0 else _WEIGHT_KG)
            for item in order.items),
        0.5
    )
    weight_grams = int(weight_kg * 1000)
    products     = ", ".join(item.book_title for item in order.items)[:100]

    payload = {
        "shipments": [{
            "name":          order.customer_name,
            "add":           order.address,
            "pin":           str(order.pincode),
            "city":          order.city or "",
            "state":         order.state or "",
            "country":       "India",
            "phone":         order.customer_phone,
            "order":         order.order_number,
            "payment_mode":  "Prepaid",
            "cod_amount":    0,
            "total_amount":  float(order.total_amount),
            "products_desc": products,
            "hsn_code":      "4901",
            "quantity":      total_qty,
            "weight":        weight_grams,
            "shipping_mode": _SHIP_MODE,
            "seller_name":   _RETURN_NAME,
            "seller_add":    _RETURN_ADDR,
            "return_pin":    _ORIGIN_PIN,
            "return_city":   _RETURN_CITY,
            "return_state":  _RETURN_STATE,
            "return_country":"India",
            "return_phone":  _RETURN_PHONE,
            "return_add":    _RETURN_ADDR,
        }],
        "pickup_location": {"name": _PICKUP_LOC}
    }

    try:
        r = requests.post(
            _BASE + "/api/cmu/create.json",
            data={"format": "json", "data": json.dumps(payload)},
            headers=_auth(),
            timeout=15,
        )
        data = r.json()
        pkgs = data.get("packages", [])
        if pkgs:
            waybill = pkgs[0].get("waybill")
            if waybill:
                return waybill, None
            remarks = pkgs[0].get("remarks", [])
            return None, remarks[0] if remarks else data.get("rmk", "Booking failed")
        return None, data.get("rmk", "Booking failed — no packages in response")
    except Exception as e:
        return None, str(e)


def track_shipment(waybill):
    """
    Fetch live tracking for a waybill.
    Returns (result_dict, error_str).
    result_dict: {status, instructions, scans: [{scan, location, datetime}]}
    """
    url = _BASE + "/api/v1/packages/json/?waybill=" + str(waybill) + "&verbose=1"
    try:
        r = requests.get(url, headers=_auth(), timeout=_TIMEOUT)
        shipment = r.json().get("ShipmentData", [{}])[0].get("Shipment", {})
        status_obj = shipment.get("Status", {})
        scans = []
        for s in shipment.get("Scans", []):
            d = s.get("ScanDetail", {})
            scans.append({
                "scan":        d.get("Scan", ""),
                "instructions":d.get("Instructions", ""),
                "location":    d.get("ScannedLocation", ""),
                "datetime":    d.get("ScanDateTime", ""),
            })
        return {
            "status":       status_obj.get("Status", ""),
            "instructions": status_obj.get("Instructions", ""),
            "scans":        list(reversed(scans)),
        }, None
    except Exception as e:
        return None, str(e)


def cancel_shipment(waybill):
    """
    Cancel a booked Delhivery shipment.
    Returns (success_bool, message_str).
    """
    try:
        r = requests.post(
            _BASE + "/api/p/edit",
            data={"waybill": waybill, "cancellation": "true"},
            headers=_auth(),
            timeout=_TIMEOUT,
        )
        body = r.text.strip() if r.text else ""

        # Delhivery sometimes returns empty body or plain text instead of JSON
        if not body:
            if r.status_code == 200:
                return True, "Shipment cancellation request sent (no response body)"
            return False, f"Delhivery returned empty response (HTTP {r.status_code})"

        try:
            data = r.json()
        except ValueError:
            # Plain-text or HTML response — treat 200 as success
            if r.status_code == 200:
                return True, body[:200]
            return False, f"Unexpected response (HTTP {r.status_code}): {body[:200]}"

        if data.get("status"):
            return True, data.get("message", "Shipment cancelled successfully")
        return False, data.get("message", "Cancellation failed")
    except Exception as e:
        return False, str(e)
