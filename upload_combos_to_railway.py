"""
Upload combo images to Railway live site.
Usage: python upload_combos_to_railway.py
"""
import os
import requests

RAILWAY_URL = "https://iskconbooks.in/admin/receive-image"
TOKEN = "iskcon-img-sync-2024"
LOCAL_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "images", "combos")

if not os.path.exists(LOCAL_FOLDER):
    print("Local combos folder not found!")
    exit(1)

files = [f for f in os.listdir(LOCAL_FOLDER) if os.path.isfile(os.path.join(LOCAL_FOLDER, f))]

print(f"Found {len(files)} combo images to upload")
ok, fail = 0, 0

for filename in files:
    filepath = os.path.join(LOCAL_FOLDER, filename)
    with open(filepath, "rb") as fh:
        try:
            resp = requests.post(RAILWAY_URL, data={
                "token": TOKEN,
                "filename": filename,
                "target": "combos",
            }, files={"file": (filename, fh)}, timeout=30)
            if resp.status_code == 200:
                print(f"  OK: {filename}")
                ok += 1
            else:
                print(f"  FAIL ({resp.status_code}): {filename}")
                fail += 1
        except Exception as e:
            print(f"  ERROR: {filename} ({e})")
            fail += 1

print(f"\nDone! Uploaded: {ok} | Failed: {fail}")
