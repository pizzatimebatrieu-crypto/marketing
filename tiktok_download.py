"""
Tai du lieu analytics TikTok Studio (pizza.time.qnhon.tuyhoa).

Cai dat (chay 1 lan):
    pip install playwright
    playwright install chromium

Cach dung:
    python tiktok_download.py

Lan dau: cua so trinh duyet mo ra, ban dang nhap TikTok bang tay, sau do quay lai
terminal bam Enter. Phien dang nhap duoc luu trong thu muc tiktok_profile/ nen
nhung lan sau se tu dong dang nhap.

Ket qua nam trong thu muc tiktok_data/:
    - cac file *.json : du lieu API ma trang analytics tai ve (da bat tu dong)
    - cac file tai ve bang nut "Download data" (neu tim thay nut)
    - trang_analytics.png : anh chup trang de kiem tra
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ANALYTICS_URL = "https://www.tiktok.com/tiktokstudio/analytics"
PROFILE_DIR = Path("tiktok_profile")
OUT_DIR = Path("tiktok_data")
OUT_DIR.mkdir(exist_ok=True)

# Chi luu cac response JSON co duong dan lien quan den analytics / thong ke
KEYWORDS = ("analytics", "aweme", "overview", "insight", "metric", "stats", "creator")


def ten_file(url: str, idx: int) -> str:
    path = re.sub(r"https?://[^/]+", "", url).split("?")[0]
    path = re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_")[-80:]
    return f"{idx:03d}_{path}.json"


def da_dang_nhap(page) -> bool:
    """Neu bi chuyen sang trang login thi chua dang nhap."""
    return "login" not in page.url and "tiktokstudio" in page.url


def main():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUT_DIR / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    saved = []

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
            accept_downloads=True,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # ---------- BUOC 1: DANG NHAP ----------
        page.goto(ANALYTICS_URL, wait_until="domcontentloaded")
        time.sleep(4)
        if not da_dang_nhap(page):
            print(">>> Chua dang nhap. Hay dang nhap TikTok trong cua so vua mo.")
            input(">>> Dang nhap xong va thay trang Analytics thi bam Enter o day... ")
            page.goto(ANALYTICS_URL, wait_until="domcontentloaded")
        print("Da dang nhap.")

        # ---------- BUOC 2: TAI DU LIEU ----------
        # Bat cac response JSON trong luc trang analytics tai du lieu
        def on_response(resp):
            try:
                url = resp.url
                ct = resp.headers.get("content-type", "")
                if "json" not in ct or not any(k in url.lower() for k in KEYWORDS):
                    return
                data = resp.json()
                f = run_dir / ten_file(url, len(saved))
                f.write_text(
                    json.dumps({"url": url, "data": data}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                saved.append(f.name)
            except Exception:
                pass

        page.on("response", on_response)

        # Tai lai trang + di qua cac tab de trang goi het API
        page.goto(ANALYTICS_URL, wait_until="networkidle")
        time.sleep(5)
        for tab in ("Overview", "Content", "Viewers", "Followers", "Tổng quan",
                    "Nội dung", "Người xem", "Người theo dõi"):
            try:
                page.get_by_role("tab", name=tab).first.click(timeout=2000)
                page.wait_for_load_state("networkidle")
                time.sleep(3)
            except Exception:
                try:
                    page.get_by_text(tab, exact=True).first.click(timeout=1500)
                    page.wait_for_load_state("networkidle")
                    time.sleep(3)
                except Exception:
                    pass

        page.screenshot(path=str(run_dir / "trang_analytics.png"), full_page=True)

        # Thu bam nut "Download data" cua TikTok Studio de lay file CSV/XLSX
        for label in ("Download data", "Tải xuống dữ liệu", "Download", "Tải xuống"):
            try:
                btn = page.get_by_role("button", name=label).first
                btn.wait_for(timeout=3000)
                with page.expect_download(timeout=30000) as dl_info:
                    btn.click()
                    # Mot so phien ban hien menu chon khoang thoi gian / dinh dang
                    for confirm in ("Download", "Tải xuống", "Confirm", "Xác nhận"):
                        try:
                            page.get_by_role("button", name=confirm).last.click(timeout=1500)
                            break
                        except Exception:
                            pass
                dl = dl_info.value
                dest = run_dir / dl.suggested_filename
                dl.save_as(str(dest))
                saved.append(dest.name)
                print("Da tai file:", dest.name)
                break
            except Exception:
                continue

        ctx.close()

    print(f"\nXong. Luu {len(saved)} file vao: {run_dir.resolve()}")
    for s in saved:
        print(" -", s)


if __name__ == "__main__":
    main()
