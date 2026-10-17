#!/usr/bin/env python3
"""Dong bo bai dang + so lieu Facebook Page vao Supabase.

Ghi vao 3 bang: fb_posts, fb_post_metrics, fb_page_daily.
<<<<<<< HEAD
Chay:  python fb_to_supabase.py [--days 30] [--dry-run] [--skip-metrics]
=======
Chay:  python fb_to_supabase.py [--page quynhon|tuyhoa] [--days 30] [--dry-run] [--skip-metrics]
>>>>>>> chia thanh 3 tab, cap nhat du lieu tiktok va tuy hoa
"""
import argparse
import hashlib
import hmac
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("fb2sb")

PAGE_ID = os.getenv("FB_PAGE_ID", "")
PAGE_TOKEN = os.getenv("FB_PAGE_TOKEN", "")
APP_SECRET = os.getenv("FB_APP_SECRET", "")
API_VERSION = os.getenv("FB_API_VERSION", "v23.0")
SB_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SB_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

BASE = f"https://graph.facebook.com/{API_VERSION}"
VN_TZ = timezone(timedelta(hours=7))

# ---- Cau hinh co the sua ---------------------------------------------------
# Cua hang duoc nhan dien qua hashtag trong noi dung bai, vd "#DH", "#hxh".
# Bai khong co tag, hoac co nhieu hon 1 tag khac nhau -> 'chung'.
STORE_TAGS = ["DH", "NH", "HXH", "PY"]
DEFAULT_STORE = "chung"

# Ten metric cua Meta -> cot trong fb_post_metrics. Meta hay doi/ngung metric,
# metric nao loi se de NULL va khong lam hong cac metric khac.
POST_METRICS = {
    "post_media_view": "media_views",
    "post_total_media_view_unique": "unique_viewers",
    "post_clicks": "clicks",
}
PAGE_DAILY_METRIC = "page_media_view"
# Gia tri 'day' cua insights period=day: Meta tra end_time la thoi diem KET THUC
# cua ngay do, nen lui 1 ngay. Dat 0 neu ban muon dung nguyen ngay cua end_time.
PAGE_DAILY_SHIFT_DAYS = 1
# ---------------------------------------------------------------------------

_SESSION = requests.Session()
_metric_fail: dict[str, int] = {}
_metric_ok: set[str] = set()


class FBError(RuntimeError):
    def __init__(self, status, message, code=None):
        super().__init__(f"FB {status} (code {code}): {message}")
        self.status = status
        self.code = code


# ---------------------------------------------------------------- Facebook --
def _auth() -> dict:
    p = {"access_token": PAGE_TOKEN}
    if APP_SECRET:
        p["appsecret_proof"] = hmac.new(
            APP_SECRET.encode(), PAGE_TOKEN.encode(), hashlib.sha256
        ).hexdigest()
    return p


def fb_get(path: str | None = None, params: dict | None = None, url: str | None = None) -> dict:
    """GET Graph API, tu thu lai khi bi rate limit. Khong bao gio in token."""
    if url is None:
        params = {**(params or {}), **_auth()}
        url = f"{BASE}/{path}"
        params_arg = params
    else:
        params_arg = None  # URL 'next' da kem san access_token
    for attempt in range(4):
        r = _SESSION.get(url, params=params_arg, timeout=30)
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code < 400 and "error" not in data:
            return data
        err = data.get("error", {})
        code = err.get("code")
        if code in (4, 17, 32, 613) or r.status_code >= 500:
            wait = 5 * 2**attempt
            log.warning("FB tam bi gioi han (code %s), cho %ss", code, wait)
            time.sleep(wait)
            continue
        raise FBError(r.status_code, err.get("message", "loi khong ro"), code)
    raise FBError(429, "het so lan thu lai")


def classify_store(message: str | None) -> str:
    if not message:
        return DEFAULT_STORE
    found = {
        m.upper()
        for m in re.findall(r"(?<![A-Za-z0-9])#([A-Za-z0-9]+)", message)
        if m.upper() in STORE_TAGS
    }
    return found.pop() if len(found) == 1 else DEFAULT_STORE


def post_type_of(p: dict) -> str:
    att = (p.get("attachments") or {}).get("data") or []
    if att and att[0].get("media_type"):
        return att[0]["media_type"]
    return "status"


# Thu lan luot tu day du -> toi thieu. Thieu quyen pages_read_user_content (code 10)
# thi bo reactions/comments (de NULL) de van lay duoc bai dang.
POST_FIELD_TIERS = [
    "id,message,created_time,permalink_url,shares,attachments{media_type},"
    "reactions.summary(true).limit(0),comments.summary(true).limit(0)",
    "id,message,created_time,permalink_url,shares,attachments{media_type}",
    "id,message,created_time,permalink_url",
]


def fetch_posts(since: datetime) -> list[dict]:
    for i, fields in enumerate(POST_FIELD_TIERS):
        try:
            data = fb_get(
                f"{PAGE_ID}/published_posts",
                {"fields": fields, "since": int(since.timestamp()), "limit": 50},
            )
        except FBError as e:
            if e.code == 10 and i < len(POST_FIELD_TIERS) - 1:
                log.warning("Thieu quyen cho bo truong #%d (%s) - thu bo truong don gian hon", i + 1, e)
                continue
            raise
        if i:
            log.warning("CHU Y: dang chay che do giam quyen (reactions/comments se la NULL). "
                        "Cap quyen pages_read_user_content roi tao lai token de du so lieu.")
        out = []
        while True:
            out.extend(data.get("data", []))
            nxt = data.get("paging", {}).get("next")
            if not nxt:
                return out
            data = fb_get(url=nxt)
    return []


def _count(p: dict, key: str):
    """So luong reactions/comments; None neu truong khong duoc tra ve (thieu quyen)."""
    if key not in p:
        return None
    return (p[key] or {}).get("summary", {}).get("total_count", 0)


def _insight_values(data: dict) -> dict:
    res = {}
    for item in data.get("data", []):
        vals = item.get("values") or []
        if vals and isinstance(vals[0].get("value"), (int, float)):
            res[item["name"]] = int(vals[0]["value"])
    return res


def fetch_post_insights(post_id: str) -> dict:
    """Tra ve {cot: gia_tri|None}. Metric loi lien tuc se bi bo qua cho cac bai sau."""
    out = {col: None for col in POST_METRICS.values()}
    live = [m for m in POST_METRICS if _metric_fail.get(m, 0) < 5 or m in _metric_ok]
    if not live:
        return out
    try:
        got = _insight_values(fb_get(f"{post_id}/insights", {"metric": ",".join(live), "period": "lifetime"}))
        for m in live:
            if m in got:
                out[POST_METRICS[m]] = got[m]
                _metric_ok.add(m)
        return out
    except FBError as e:
        if e.code in (10, 190, 200):  # thieu quyen / token loi -> dung han
            raise
    for m in live:  # thu tung metric de biet metric nao hong
        try:
            got = _insight_values(fb_get(f"{post_id}/insights", {"metric": m, "period": "lifetime"}))
            if m in got:
                out[POST_METRICS[m]] = got[m]
                _metric_ok.add(m)
        except FBError as e:
            _metric_fail[m] = _metric_fail.get(m, 0) + 1
            log.debug("metric %s loi cho %s: %s", m, post_id, e)
    return out


def fetch_page_daily(days: int) -> list[dict]:
    rows: dict[str, int] = {}
    end = datetime.now(timezone.utc) + timedelta(days=1)
    start = end - timedelta(days=days + 1)
    cur = start
    while cur < end:  # Meta gioi han ~93 ngay moi lan goi
        nxt = min(cur + timedelta(days=90), end)
        data = fb_get(
            f"{PAGE_ID}/insights",
            {"metric": PAGE_DAILY_METRIC, "period": "day",
             "since": int(cur.timestamp()), "until": int(nxt.timestamp())},
        )
        for item in data.get("data", []):
            for v in item.get("values", []):
                if isinstance(v.get("value"), (int, float)) and v.get("end_time"):
                    t = datetime.strptime(v["end_time"], "%Y-%m-%dT%H:%M:%S%z")
                    day = (t - timedelta(days=PAGE_DAILY_SHIFT_DAYS)).astimezone(timezone.utc).date()
                    rows[day.isoformat()] = int(v["value"])
        cur = nxt
<<<<<<< HEAD
    return [{"day": d, "media_views": v} for d, v in sorted(rows.items())]
=======
    return [{"page_id": PAGE_ID, "day": d, "media_views": v} for d, v in sorted(rows.items())]
>>>>>>> chia thanh 3 tab, cap nhat du lieu tiktok va tuy hoa


# ---------------------------------------------------------------- Supabase --
def sb_upsert(table: str, rows: list[dict], on_conflict: str, ignore_dup: bool = False) -> None:
    if not rows:
        return
    resolution = "ignore-duplicates" if ignore_dup else "merge-duplicates"
    headers = {
        "apikey": SB_KEY,
        "Authorization": f"Bearer {SB_KEY}",
        "Content-Type": "application/json",
        "Prefer": f"resolution={resolution},return=minimal",
    }
    for i in range(0, len(rows), 200):
        r = requests.post(
            f"{SB_URL}/rest/v1/{table}",
            params={"on_conflict": on_conflict},
            headers=headers,
            json=rows[i : i + 200],
            timeout=60,
        )
        if r.status_code >= 300:
            raise RuntimeError(f"Supabase {table} {r.status_code}: {r.text[:300]}")


# -------------------------------------------------------------------- main --
def build_rows(posts: list[dict]) -> tuple[list[dict], list[dict]]:
    new_rows, base_rows = [], []
    for p in posts:
        base = {
            "id": p["id"],
            "message": p.get("message"),
            "post_type": post_type_of(p),
            "created_time": p.get("created_time"),
            "permalink_url": p.get("permalink_url"),
        }
        base_rows.append(base)
        new_rows.append({**base, "store": classify_store(p.get("message"))})
    return new_rows, base_rows


def run(days: int, dry: bool, skip_metrics: bool) -> int:
    missing = [n for n, v in [("FB_PAGE_ID", PAGE_ID), ("FB_PAGE_TOKEN", PAGE_TOKEN),
                              ("SUPABASE_URL", SB_URL), ("SUPABASE_SERVICE_KEY", SB_KEY)] if not v]
    if missing and not dry:
        log.error("Thieu bien moi truong: %s", ", ".join(missing))
        return 2

    since = datetime.now(timezone.utc) - timedelta(days=days)
    posts = fetch_posts(since)
    log.info("Lay %d bai trong %d ngay", len(posts), days)

    new_rows, base_rows = build_rows(posts)
    snap = datetime.now(VN_TZ).date().isoformat()
    metric_rows = []
    for i, p in enumerate(posts, 1):
        row = {
            "post_id": p["id"],
            "snapshot_date": snap,
            "media_views": None, "unique_viewers": None, "clicks": None,
            "reactions": _count(p, "reactions"),
            "comments": _count(p, "comments"),
            "shares": (p.get("shares") or {}).get("count", 0),
        }
        if not skip_metrics:
            row.update(fetch_post_insights(p["id"]))
            time.sleep(0.2)
        metric_rows.append(row)
        if i % 20 == 0:
            log.info("  insights %d/%d", i, len(posts))

<<<<<<< HEAD
    daily = fetch_page_daily(max(days, 30))
=======
    daily = fetch_page_daily(min(max(days * 2, 30), 700))  # x2 de co ky truoc so sanh
>>>>>>> chia thanh 3 tab, cap nhat du lieu tiktok va tuy hoa
    log.info("Page daily: %d ngay", len(daily))

    if dry:
        log.info("DRY-RUN: khong ghi Supabase. Mau fb_posts: %s", new_rows[:2])
        log.info("Mau fb_post_metrics: %s", metric_rows[:2])
        log.info("Mau fb_page_daily: %s", daily[:2])
        return 0

    # 1) bai moi: chen kem 'store' tu dong; bai da co thi bo qua (giu store ban da sua tay)
    sb_upsert("fb_posts", new_rows, "id", ignore_dup=True)
    # 2) bai da co: cap nhat noi dung/loai/link, KHONG dong vao cot store
    sb_upsert("fb_posts", base_rows, "id")
    sb_upsert("fb_post_metrics", metric_rows, "post_id,snapshot_date")
<<<<<<< HEAD
    sb_upsert("fb_page_daily", daily, "day")
=======
    sb_upsert("fb_page_daily", daily, "page_id,day")
>>>>>>> chia thanh 3 tab, cap nhat du lieu tiktok va tuy hoa
    bad = [m for m, n in _metric_fail.items() if n >= 5 and m not in _metric_ok]
    if bad:
        log.warning("Metric khong lay duoc (de NULL): %s - sua POST_METRICS neu Meta da doi ten", bad)
    log.info("Xong: %d bai, %d dong metrics, %d ngay page", len(posts), len(metric_rows), len(daily))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
<<<<<<< HEAD
=======
    ap.add_argument("--page", choices=["quynhon", "tuyhoa"], default="quynhon",
                    help="page can dong bo; doc FB_PAGE_ID_<PAGE>/FB_PAGE_TOKEN_<PAGE> trong .env")
>>>>>>> chia thanh 3 tab, cap nhat du lieu tiktok va tuy hoa
    ap.add_argument("--days", type=int, default=30, help="so ngay bai dang gan nhat (mac dinh 30)")
    ap.add_argument("--dry-run", action="store_true", help="chi doc Facebook, khong ghi Supabase")
    ap.add_argument("--skip-metrics", action="store_true", help="bo qua insights tung bai (chay nhanh)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
<<<<<<< HEAD
=======
    global PAGE_ID, PAGE_TOKEN
    suffix = a.page.upper()
    PAGE_ID = os.getenv(f"FB_PAGE_ID_{suffix}") or (os.getenv("FB_PAGE_ID", "") if a.page == "quynhon" else "")
    PAGE_TOKEN = os.getenv(f"FB_PAGE_TOKEN_{suffix}") or (os.getenv("FB_PAGE_TOKEN", "") if a.page == "quynhon" else "")
>>>>>>> chia thanh 3 tab, cap nhat du lieu tiktok va tuy hoa
    try:
        return run(a.days, a.dry_run, a.skip_metrics)
    except (FBError, RuntimeError, requests.RequestException) as e:
        log.error("%s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
