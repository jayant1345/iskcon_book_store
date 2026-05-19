# -*- coding: utf-8 -*-
"""Quick debug: print raw serviceability JSON to see actual field names."""
import os, json, requests
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.environ.get("DELHIVERY_API_TOKEN", "")
URL   = "https://track.delhivery.com/c/api/pin-codes/json/?filter_codes=400001"
r = requests.get(URL, headers={"Authorization": "Token " + TOKEN}, timeout=10)
print("HTTP:", r.status_code)
print(json.dumps(r.json(), indent=2))
