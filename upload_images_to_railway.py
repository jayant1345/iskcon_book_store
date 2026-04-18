"""
Upload local book cover images to Railway's persistent volume.
Run once: python upload_images_to_railway.py
"""
import os
import requests

RAILWAY_URL = "https://iskconbooks.in/admin/receive-image"
TOKEN = "iskcon-img-sync-2024"
LOCAL_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "images", "books")

files = [f for f in os.listdir(LOCAL_FOLDER)
         if f != "default_book.jpg" and os.path.isfile(os.path.join(LOCAL_FOLDER, f))]

print(f"Found {len(files)} images to upload")
ok, fail = 0, 0

for filename in files:
    filepath = os.path.join(LOCAL_FOLDER, filename)
    with open(filepath, "rb") as fh:
        resp = requests.post(RAILWAY_URL, data={
            "token": TOKEN,
            "filename": filename,
        }, files={"file": (filename, fh)}, timeout=30)
    if resp.status_code == 200:
        print(f"  OK: {filename}")
        ok += 1
    else:
        print(f"  FAIL ({resp.status_code}): {filename}")
        fail += 1

print(f"\nDone! Uploaded: {ok} | Failed: {fail}")
