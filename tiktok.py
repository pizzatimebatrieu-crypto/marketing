"""Doc data/data-tiktok.csv (xuat tu TikTok Studio) de day len Supabase, va tinh so lieu tong hop."""
import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

VN = timezone(timedelta(hours=7))
CSV_PATH = Path(__file__).parent / "data" / "data-tiktok.csv"
MONTHS = {"Một": 1, "Hai": 2, "Ba": 3, "Tư": 4, "Năm": 5, "Sáu": 6, "Bảy": 7,
          "Tám": 8, "Chín": 9, "Mười": 10, "Mười Một": 11, "Mười Hai": 12}
WEEKDAYS = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
FIELDS = ["views", "profile", "likes", "comments", "shares"]


def _int(x):
    try:
        return int(str(x).replace(",", "").replace(".", "").strip() or 0)
    except ValueError:
        return 0


def parse_csv(path: Path, today: date) -> list[dict]:
    """File khong ghi nam: dong cuoi la ngay moi nhat (khong sau hom nay), lui dan de suy ra nam."""
    raw = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            d, _, m = (r.get("Date") or "").strip().partition(" tháng ")
            if not d.isdigit() or m.strip() not in MONTHS:
                continue
            raw.append((MONTHS[m.strip()], int(d), [_int(r.get(k)) for k in
                        ("Video Views", "Profile Views", "Likes", "Comments", "Shares")]))
    if not raw:
        return []
    month, day, _ = raw[-1]
    year = today.year
    while True:
        try:
            if date(year, month, day) <= today:
                break
        except ValueError:
            pass
        year -= 1
    rows, cur = [], date(year, month, day)
    for i, (_, _, vals) in enumerate(reversed(raw)):
        rows.append({"date": cur - timedelta(days=i), **dict(zip(FIELDS, vals))})
    rows.reverse()
    return rows


def _tot(rows):
    return {k: sum(r[k] for r in rows) for k in FIELDS}


def _chg(cur, prev):
    return None if not prev else (cur - prev) / prev * 100


def _ratio(a, b):
    return a / b if b else None


def from_db(db_rows: list[dict]) -> list[dict]:
    """Dong tu bang tiktok_daily (Supabase) -> cung dang voi parse_csv."""
    return [{"date": date.fromisoformat(r["day"]), "views": r["video_views"], "profile": r["profile_views"],
             "likes": r["likes"], "comments": r["comments"], "shares": r["shares"]} for r in db_rows]


def build_summary(rows: list[dict], today: date, days: int, start: date | None, end: date | None) -> dict:
    if not rows:
        return {"empty": True}
    first, last = rows[0]["date"], rows[-1]["date"]
    end = min(end or last, last)
    if start:
        days = (end - start).days + 1
    days = max(1, days)
    win_start = end - timedelta(days=days - 1)
    cur = [r for r in rows if win_start <= r["date"] <= end]
    prev = [r for r in rows if win_start - timedelta(days=days) <= r["date"] < win_start]

    series = [r["views"] for r in rows]
    ma7 = {r["date"]: round(sum(series[max(0, i - 6):i + 1]) / len(series[max(0, i - 6):i + 1]))
           for i, r in enumerate(rows)}

    t, p = _tot(cur), _tot(prev)
    inter = t["likes"] + t["comments"] + t["shares"]
    pinter = p["likes"] + p["comments"] + p["shares"]
    kpi = {
        **t, "interactions": inter,
        "engagement": _ratio(inter, t["views"]),
        "profile_rate": _ratio(t["profile"], t["views"]),
        "avg_views": _ratio(t["views"], len(cur)),
        "change": {**{k: _chg(t[k], p[k]) for k in FIELDS}, "interactions": _chg(inter, pinter)} if prev else {},
    }

    wd = [[] for _ in range(7)]
    for r in cur:
        wd[r["date"].weekday()].append(r)
    by_weekday = [{"label": WEEKDAYS[i], "days": len(g),
                   "avg_views": round(sum(x["views"] for x in g) / len(g)) if g else 0,
                   "avg_inter": round(sum(x["likes"] + x["comments"] + x["shares"] for x in g) / len(g)) if g else 0}
                  for i, g in enumerate(wd)]

    months: dict[str, dict] = {}
    for r in cur:
        m = months.setdefault(r["date"].strftime("%Y-%m"), dict.fromkeys(FIELDS, 0))
        for k in FIELDS:
            m[k] += r[k]
    by_month = [{"month": k, **v} for k, v in sorted(months.items())]

    top = sorted(cur, key=lambda r: r["views"], reverse=True)[:10]
    notes = []
    if end < today - timedelta(days=1):
        notes.append(f"Dữ liệu TikTok mới đến ngày {last.strftime('%d/%m/%Y')}.")
    notes.append("Số liệu theo ngày từ TikTok Studio (không có chi tiết từng video).")
    return {
        "as_of": last.isoformat(), "range_days": days, "first_day": first.isoformat(),
        "kpi": kpi, "by_weekday": by_weekday, "by_month": by_month, "notes": notes,
        "daily": [{"day": r["date"].isoformat(), **{k: r[k] for k in FIELDS}, "ma7": ma7[r["date"]],
                   "interactions": r["likes"] + r["comments"] + r["shares"]} for r in cur],
        "top_days": [{"day": r["date"].isoformat(), **{k: r[k] for k in FIELDS}} for r in top],
    }
