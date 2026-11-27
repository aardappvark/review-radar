#!/usr/bin/env python3
"""Dig into the numbers: the statistics behind each app's reviews, for the page's graphs.

Adds "stats" to data/<slug>.analysis.json (runs after analyse/brief/fixes; it only adds a field):
- stars: the 1-5 star mix in the recent window and the period before it;
- monthly: written reviews, average stars, share at 1-2 stars and share reporting something broken, for the last 18 months;
- countries: where reviewers are (App Store storefront, or the merchant's country on Shopify);
- short_share: written reviews of three words or fewer (Undersigned's "a star says nothing" measure), and median length;
- replies (Shopify only): how often the publisher answers in public, overall and for 1-2 star reviews.
Usage: stats.py [slug ...]
"""
import collections, datetime as dt, json, re, statistics, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
APPS = {a["slug"]: a for a in json.loads((ROOT / "apps.json").read_text())}
CC = {"us": "United States", "gb": "United Kingdom", "ca": "Canada", "au": "Australia", "nz": "New Zealand", "ie": "Ireland"}


def words(t):
    return len([w for w in re.split(r"\s+", t.strip()) if any(c.isalnum() for c in w)])


def main(slug):
    meta = APPS[slug]
    path = DATA / f"{slug}.analysis.json"
    a = json.loads(path.read_text())
    if a.get("sample_only"):
        a["stats"] = None
        path.write_text(json.dumps(a, ensure_ascii=False, indent=1))
        return
    rows = [r for r in json.loads((DATA / f"{slug}.reviews.json").read_text()) if r["date"] >= meta["window_start"]]
    tags = json.loads((DATA / f"{slug}.tags.json").read_text())
    now = dt.datetime.now(dt.timezone.utc)
    days = a["window"].get("recent_days", 90)
    rec_from, pri_from = (now - dt.timedelta(days=days)).date().isoformat(), (now - dt.timedelta(days=2 * days)).date().isoformat()
    written = [r for r in rows if (r["body"] or r.get("title", "")).strip()]

    def mix(rs):
        c = collections.Counter(r["rating"] for r in rs)
        return [c.get(s, 0) for s in range(1, 6)]

    recent = [r for r in rows if r["date"][:10] >= rec_from]
    prior = [r for r in rows if pri_from <= r["date"][:10] < rec_from]

    # Monthly, last 18 calendar months (empty months kept so the axis is honest)
    months = []
    y, m = now.year, now.month
    for _ in range(18):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    months.reverse()
    by_m = collections.defaultdict(list)
    for r in written:
        by_m[r["date"][:7]].append(r)
    monthly = []
    for mo in months:
        rs = by_m.get(mo, [])
        monthly.append({"month": mo, "n": len(rs), "avg": round(statistics.mean(r["rating"] for r in rs), 2) if rs else None,
                        "low_share": round(sum(r["rating"] <= 2 for r in rs) / len(rs), 3) if rs else None,
                        "broken_share": round(sum(tags.get(r["id"], {}).get("bug", False) for r in rs) / len(rs), 3) if rs else None})

    cc = collections.Counter(CC.get(r["cc"], r["cc"]) or "Not given" for r in rows)
    lens = [words(r["body"]) for r in written if r["body"].strip()]
    rec_written = [r for r in written if r["date"][:10] >= rec_from]
    out = {
        "window_label": a["window"].get("recent_label", "90 days"),
        "stars": {"recent": mix(recent), "prior": mix(prior)},
        "monthly": monthly,
        "countries": [{"name": k, "n": v} for k, v in cc.most_common(8)],
        "countries_total": len(rows),
        "short_share": round(sum(words(r["body"]) <= 3 for r in written if r["body"].strip()) / len(lens), 3) if lens else None,
        "median_words": int(statistics.median(lens)) if lens else None,
        "written": len(written), "recent_written": len(rec_written),
        "replies": None,
    }
    if meta["store"] == "shopify" and rows and "replied" in rows[0]:
        low = [r for r in rows if r["rating"] <= 2]
        out["replies"] = {"all": round(sum(r["replied"] for r in rows) / len(rows), 3), "n": len(rows),
                          "low": round(sum(r["replied"] for r in low) / len(low), 3) if low else None, "low_n": len(low),
                          "recent": round(sum(r["replied"] for r in recent) / len(recent), 3) if recent else None, "recent_n": len(recent)}
    a["stats"] = out
    path.write_text(json.dumps(a, ensure_ascii=False, indent=1))
    rp = out["replies"]
    print(f"{slug}: stars recent {out['stars']['recent']} prior {out['stars']['prior']}; short {out['short_share']}, median {out['median_words']} words; "
          f"top countries {[c['name'] for c in out['countries'][:3]]}" + (f"; replies {rp['all']:.0%} overall, {rp['low']:.0%} of 1-2 star" if rp and rp['low'] is not None else ""))


if __name__ == "__main__":
    for s in sys.argv[1:] or list(APPS):
        if (DATA / f"{s}.analysis.json").exists():
            main(s)
