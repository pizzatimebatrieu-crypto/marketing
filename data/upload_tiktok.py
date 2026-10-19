"""
Day data/data-tiktok.csv (xuat tu TikTok Studio) len bang tiktok_daily tren Supabase.

Cach dung:
    python data/upload_tiktok.py [duong_dan_file.csv]

Mac dinh doc data/data-tiktok.csv (cung thu muc voi script). Ngay da co se duoc cap nhat, ngay moi se duoc them
(khong xoa du lieu cu). Can chay supabase_tiktok.sql 1 lan truoc.
"""
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import tiktok  # noqa: E402

load_dotenv(ROOT / ".env")
URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_KEY"]


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else tiktok.CSV_PATH
    today = datetime.now(tiktok.VN).date()
    rows = tiktok.parse_csv(path, today)
    if not rows:
        sys.exit(f"Khong doc duoc dong nao tu {path}")
    payload = [{"day": r["date"].isoformat(), "video_views": r["views"], "profile_views": r["profile"],
                "likes": r["likes"], "comments": r["comments"], "shares": r["shares"]} for r in rows]
    r = requests.post(f"{URL}/rest/v1/tiktok_daily", timeout=30, params={"on_conflict": "day"},
                      headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                               "Content-Type": "application/json",
                               "Prefer": "resolution=merge-duplicates,return=minimal"},
                      json=payload)
    if r.status_code >= 300:
        sys.exit(f"Loi Supabase {r.status_code}: {r.text[:300]}")
    print(f"Da day {len(payload)} ngay ({payload[0]['day']} -> {payload[-1]['day']}) len tiktok_daily")


if __name__ == "__main__":
    main()
