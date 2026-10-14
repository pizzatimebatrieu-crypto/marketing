"""Tinh toan tong hop tu du lieu Supabase (thuan Python, khong phu thuoc thu vien ngoai)."""
import re
from datetime import date, datetime, timedelta, timezone

VN = timezone(timedelta(hours=7))
WEEKDAYS = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
SLOTS = [(0, 6, "0–6h"), (6, 10, "6–10h"), (10, 14, "10–14h"),
         (14, 18, "14–18h"), (18, 22, "18–22h"), (22, 24, "22–24h")]


def parse_dt(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    s = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", s)  # +0000 -> +00:00
    try:
        return datetime.fromisoformat(s).astimezone(VN)
    except ValueError:
        return None


def _n(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _sum(vals):
    v = [x for x in vals if x is not None]
    return sum(v) if v else None


def _avg(vals):
    v = [x for x in vals if x is not None]
    return round(sum(v) / len(v)) if v else None


def short(msg, n=140):
    t = re.sub(r"\s+", " ", msg or "").strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def latest_metrics(metrics):
    best = {}
    for m in metrics:
        pid = m.get("post_id")
        if pid and (pid not in best or str(m.get("snapshot_date")) > str(best[pid].get("snapshot_date"))):
            best[pid] = m
    return best


def build_summary(posts, metrics, daily, days, today=None):
    today = today or datetime.now(VN).date()
    cutoff_dt = datetime.combine(today - timedelta(days=days - 1), datetime.min.time(), tzinfo=VN)
    end_dt = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=VN)
    last = latest_metrics(metrics)

    # ---- bai dang trong khoang
    rows = []
    for p in posts:
        ct = parse_dt(p.get("created_time"))
        if not ct or ct < cutoff_dt or ct >= end_dt:
            continue
        m = last.get(p["id"], {})
        views, uniq, clicks = _n(m.get("media_views")), _n(m.get("unique_viewers")), _n(m.get("clicks"))
        rows.append({
            "id": p["id"], "created_time": ct.isoformat(), "message": short(p.get("message")),
            "url": p.get("permalink_url"), "type": p.get("post_type") or "status",
            "views": views, "unique": uniq, "clicks": clicks,
            "ctr": round(clicks / views, 4) if views and clicks is not None else None,
            "reactions": _n(m.get("reactions")), "comments": _n(m.get("comments")),
            "shares": _n(m.get("shares")),
            "_dt": ct,
        })
    rows.sort(key=lambda r: (r["views"] is None, -(r["views"] or 0)))

    # ---- page theo ngay
    series = sorted(
        ({"day": d["day"], "media_views": _n(d.get("media_views"))} for d in daily if d.get("day")),
        key=lambda x: x["day"],
    )
    vals = [s["media_views"] or 0 for s in series]
    for i, s in enumerate(series):
        s["ma7"] = round(sum(vals[i - 6: i + 1]) / 7) if i >= 6 else None

    d_end = today.isoformat()
    d_start = (today - timedelta(days=days)).isoformat()
    d_prev = (today - timedelta(days=2 * days)).isoformat()
    cur = [s for s in series if d_start < s["day"] <= d_end]
    prev = [s for s in series if d_prev < s["day"] <= d_start]
    pv = sum(s["media_views"] or 0 for s in cur) if cur else None
    pv_prev = sum(s["media_views"] or 0 for s in prev) if len(prev) >= days else None
    change = round((pv - pv_prev) / pv_prev * 100, 1) if pv is not None and pv_prev else None

    views_sum = _sum(r["views"] for r in rows)
    clicks_sum = _sum(r["clicks"] for r in rows)
    has_eng = any(r["reactions"] is not None or r["comments"] is not None for r in rows)

    def group(keyfn, order):
        g = {}
        for r in rows:
            if r["views"] is None:
                continue
            g.setdefault(keyfn(r), []).append(r["views"])
        return [{"label": k, "posts": len(g[k]), "avg_views": _avg(g[k]), "total_views": sum(g[k])}
                for k in order if k in g]

    def slot_of(r):
        h = r["_dt"].hour
        return next(lab for a, b, lab in SLOTS if a <= h < b)

    types = sorted({r["type"] for r in rows if r["views"] is not None})
    by_type = group(lambda r: r["type"], types)
    by_type.sort(key=lambda x: -(x["avg_views"] or 0))

    snaps = sorted({str(m.get("snapshot_date")) for m in metrics if m.get("snapshot_date")})
    notes = []
    if rows and not any(r["views"] is not None for r in rows):
        notes.append("Chưa có số liệu insights của các bài trong khoảng này.")
    if rows and not has_eng:
        notes.append("Reaction và bình luận chưa có: token thiếu quyền pages_read_user_content.")
    if len(snaps) < 2:
        notes.append("Mới có 1 ngày snapshot nên chưa vẽ được xu hướng theo thời gian của từng bài.")

    by_weekday = group(lambda r: WEEKDAYS[r["_dt"].weekday()], WEEKDAYS)
    by_slot = group(slot_of, [lab for _, _, lab in SLOTS])
    for r in rows:
        r.pop("_dt")
    return {
        "range_days": days,
        "as_of": snaps[-1] if snaps else None,
        "kpi": {
            "page_views": pv, "page_views_prev": pv_prev, "page_views_change_pct": change,
            "posts": len(rows), "post_views": views_sum,
            "unique_sum": _sum(r["unique"] for r in rows), "clicks": clicks_sum,
            "ctr": round(clicks_sum / views_sum, 4) if views_sum and clicks_sum is not None else None,
            "reactions": _sum(r["reactions"] for r in rows),
            "comments": _sum(r["comments"] for r in rows),
            "shares": _sum(r["shares"] for r in rows),
            "has_engagement": has_eng,
        },
        "daily": cur,
        "by_type": by_type,
        "by_weekday": by_weekday,
        "by_slot": by_slot,
        "posts": rows,
        "notes": notes,
    }
