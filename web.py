"""Web tong hop thong tin Facebook Page: doc Supabase phia server, hien thi dashboard.

Chay local:  uvicorn web:app --host 127.0.0.1 --port 8090
Deploy Vercel: entrypoint index.py. Dang nhap bang bang web_users (Supabase) + cookie JWT.
Bien moi truong: SUPABASE_URL, SUPABASE_SERVICE_KEY, SESSION_SECRET.
"""
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt
import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

import agg

load_dotenv()
SB_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SB_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "7"))
COOKIE_SECURE = bool(os.getenv("VERCEL")) or os.getenv("COOKIE_SECURE") == "1"
COOKIE_NAME = "fb_session"
MAX_FAILS, LOCK_MINUTES = 5, 15
MAX_DAYS = 730
CACHE_SECONDS = int(os.getenv("WEB_CACHE_SECONDS", "60"))

_missing = [n for n, v in [("SUPABASE_URL", SB_URL), ("SUPABASE_SERVICE_KEY", SB_KEY),
                           ("SESSION_SECRET", SESSION_SECRET)] if not v]
if _missing:
    raise RuntimeError("Thieu bien trong .env: " + ", ".join(_missing))

app = FastAPI(title="FB Page Hub", docs_url=None, redoc_url=None, openapi_url=None)
STATIC = Path(__file__).parent / "static"
_cache: dict = {}


SB_HEADERS = {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}"}
# hash gia de van ton thoi gian bcrypt khi username khong ton tai (tranh do ra user)
_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt())


def current_user(request: Request) -> str | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        return jwt.decode(token, SESSION_SECRET, algorithms=["HS256"]).get("sub")
    except jwt.PyJWTError:
        return None


def require_user(request: Request) -> str:
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Chua dang nhap")
    return user


class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=200)


@app.post("/api/login", include_in_schema=False)
def login(body: LoginIn):
    username = body.username.strip().lower()
    now = datetime.now(timezone.utc)
    r = requests.get(f"{SB_URL}/rest/v1/web_users", headers=SB_HEADERS, timeout=15, params={
        "select": "id,password_hash,is_active,failed_count,locked_until",
        "username": f"eq.{username}", "limit": 1})
    if r.status_code >= 300:
        raise HTTPException(502, "Khong doc duoc bang web_users")
    rows = r.json()
    user = rows[0] if rows else None

    if user:
        locked = agg.parse_dt(user.get("locked_until"))
        if locked and locked > now:
            raise HTTPException(429, f"Sai qua nhieu lan, thu lai sau {LOCK_MINUTES} phut")

    hashed = user["password_hash"].encode() if user else _DUMMY_HASH
    pw_ok = bcrypt.checkpw(body.password.encode()[:72], hashed)
    if not (user and user["is_active"] and pw_ok):
        if user:
            fails = (user.get("failed_count") or 0) + 1
            patch = {"failed_count": fails}
            if fails >= MAX_FAILS:
                patch = {"failed_count": 0, "locked_until": (now + timedelta(minutes=LOCK_MINUTES)).isoformat()}
            requests.patch(f"{SB_URL}/rest/v1/web_users", headers=SB_HEADERS, timeout=15,
                           params={"id": f"eq.{user['id']}"}, json=patch)
        raise HTTPException(401, "Sai tai khoan hoac mat khau")

    if user.get("failed_count"):
        requests.patch(f"{SB_URL}/rest/v1/web_users", headers=SB_HEADERS, timeout=15,
                       params={"id": f"eq.{user['id']}"}, json={"failed_count": 0, "locked_until": None})

    token = jwt.encode({"sub": username, "exp": now + timedelta(days=SESSION_DAYS)},
                       SESSION_SECRET, algorithm="HS256")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(COOKIE_NAME, token, max_age=SESSION_DAYS * 86400, httponly=True,
                    secure=COOKIE_SECURE, samesite="lax", path="/")
    return resp


@app.post("/api/logout", include_in_schema=False)
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


def sb_select(table: str, params: dict) -> list[dict]:
    """Doc het cac dong (PostgREST gioi han 1000 dong/lan)."""
    headers = SB_HEADERS
    out, start = [], 0
    while True:
        r = requests.get(
            f"{SB_URL}/rest/v1/{table}", params=params, timeout=30,
            headers={**headers, "Range-Unit": "items", "Range": f"{start}-{start + 999}"},
        )
        if r.status_code >= 300:
            raise HTTPException(502, f"Supabase {table}: {r.status_code} {r.text[:200]}")
        rows = r.json()
        out.extend(rows)
        if len(rows) < 1000:
            return out
        start += 1000


def cached(key, fn):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    val = fn()
    _cache[key] = (now, val)
    return val


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    if current_user(request):
        return RedirectResponse("/", status_code=303)
    return FileResponse(STATIC / "login.html")


@app.get("/", include_in_schema=False)
def index(request: Request):
    if not current_user(request):
        return RedirectResponse("/login", status_code=303)
    return FileResponse(STATIC / "index.html")


@app.get("/api/summary", dependencies=[Depends(require_user)])
def summary(days: int = 30, start: date | None = None, end: date | None = None):
    real_today = datetime.now(agg.VN).date()
    end = min(end or real_today, real_today)
    if start:
        if start > end:
            raise HTTPException(400, "Ngay bat dau phai truoc ngay ket thuc")
        days = (end - start).days + 1
    days = max(1, min(days, MAX_DAYS))

    def load():
        today = end
        since_post = (today - timedelta(days=days + 1)).isoformat()
        since_day = (today - timedelta(days=2 * days + 1)).isoformat()
        posts = sb_select("fb_posts", {"select": "id,message,post_type,created_time,permalink_url",
                                       "created_time": f"gte.{since_post}", "order": "created_time.desc"})
        metrics = sb_select("fb_post_metrics", {"select": "*", "order": "snapshot_date.asc"})
        daily = sb_select("fb_page_daily", {"select": "day,media_views", "day": f"gte.{since_day}",
                                            "order": "day.asc"})
        return agg.build_summary(posts, metrics, daily, days, today)

    return cached(("summary", days, end), load)


@app.get("/api/post/{post_id}", dependencies=[Depends(require_user)])
def post_trend(post_id: str):
    if not re.fullmatch(r"[0-9_]{5,64}", post_id):
        raise HTTPException(400, "post_id khong hop le")
    rows = cached(("post", post_id), lambda: sb_select(
        "fb_post_metrics",
        {"select": "snapshot_date,media_views,unique_viewers,clicks,reactions,comments,shares",
         "post_id": f"eq.{post_id}", "order": "snapshot_date.asc"}))
    return rows
