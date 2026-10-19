"""Tao user hoac doi mat khau (chay tren may ban, doc .env cung thu muc).

  python create_user.py <username>
  python create_user.py <username> --off    # khoa tai khoan
"""
import getpass
import os
import sys

import bcrypt
import requests
from dotenv import load_dotenv

load_dotenv()
URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_KEY"]
H = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}

if len(sys.argv) < 2:
    sys.exit(__doc__)
username = sys.argv[1].strip().lower()

if "--off" in sys.argv:
    r = requests.patch(f"{URL}/rest/v1/web_users", headers=H, params={"username": f"eq.{username}"},
                       json={"is_active": False})
    sys.exit(f"Da khoa {username}" if r.ok else f"Loi {r.status_code}: {r.text}")

pw = getpass.getpass("Mat khau (>= 8 ky tu): ")
if len(pw) < 8 or pw != getpass.getpass("Nhap lai: "):
    sys.exit("Mat khau qua ngan hoac khong khop")
hashed = bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()
r = requests.post(f"{URL}/rest/v1/web_users", params={"on_conflict": "username"},
                  headers={**H, "Prefer": "resolution=merge-duplicates"},
                  json={"username": username, "password_hash": hashed, "is_active": True,
                        "failed_count": 0, "locked_until": None})
print(f"OK: {username}" if r.ok else f"Loi {r.status_code}: {r.text}")
