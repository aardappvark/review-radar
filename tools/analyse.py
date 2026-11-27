#!/usr/bin/env python3
"""Turn tagged reviews into the radar: themes + trend, version regressions, bursts, copy-paste text.

Writes data/<slug>.analysis.json. Pure stdlib, deterministic.
"""
import json, re, sys, pathlib, statistics, collections, datetime as dt, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent / "data"
APPS = {a["slug"]: a for a in json.loads((ROOT.parent / "apps.json").read_text())}
# Quotes shown on the page skip anything hostile, political or profane: evidence, not drama.
QUOTE_SKIP = re.compile(r"\b(israel|palestin|gaza|trump|biden|woke|nazi|fuck|shit|gaf|wtf|damn|bitch|idiot|retard|garbage|stupid|hate)\w*", re.I)


def parse(d):
    return dt.datetime.fromisoformat(d.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def vkey(v):
    return [int(p) if p.isdigit() else 0 for p in v.split(".")]


def clip(text, n=190):
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= n:
        return text
    cut = text[:n]
    m = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:m + 1] if m > 80 else cut.rsplit(" ", 1)[0]) + " …"


def shingles(t, k=3):
    w = re.findall(r"[a-z0-9']+", t.lower())
    return {" ".join(w[i:i + k]) for i in range(max(0, len(w) - k + 1))}


UA = {"User-Agent": "Mozilla/5.0 (Macintosh) review-radar/0.2"}


def store_stats(meta):
    if meta["store"] == "shopify":  # the app page's own JSON-LD rating
        h = urllib.request.urlopen(urllib.request.Request(f"https://apps.shopify.com/{meta['id']}", headers=UA), timeout=25).read().decode("utf-8", "replace")
        agg = {}
        for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
            try:
                d = json.loads(m)
            except ValueError:
                continue
            agg = d.get("aggregateRating") or agg
        return {"avg": round(float(agg.get("ratingValue", 0)), 2), "count": int(agg.get("ratingCount", 0)), "version": None,
                "version_date": None, "released": None, "notes": "", "store": "shopify", "url": f"https://apps.shopify.com/{meta['id']}"}
    with urllib.request.urlopen(urllib.request.Request(f"https://itunes.apple.com/lookup?id={meta['id']}&country=us", headers=UA), timeout=20) as r:
        x = json.load(r)["results"][0]
    return {"avg": round(x["averageUserRating"], 2), "count": x["userRatingCount"], "version": x["version"],
            "version_date": x["currentVersionReleaseDate"][:10], "released": x["releaseDate"][:10], "notes": x.get("releaseNotes", "")[:400],
            "store": "apple", "url": x.get("trackViewUrl", "").split("?")[0]}


def quotes(rows, k=3, max_stars=3):
    picks = [r for r in rows if r["rating"] <= max_stars and len(r["body"]) >= 40 and not QUOTE_SKIP.search(r["title"] + " " + r["body"])]
    picks.sort(key=lambda r: r["date"], reverse=True)
    return [{"stars": r["rating"], "date": r["date"][:10], "version": r["version"], "cc": r["cc"].upper(),
             "title": clip(r["title"], 60), "text": clip(r["body"])} for r in picks[:k]]


def main(slug):
    meta = APPS[slug]
    rows = json.loads((ROOT / f"{slug}.reviews.json").read_text())
    tags = json.loads((ROOT / f"{slug}.tags.json").read_text())
    themes = {t["key"]: t for t in json.loads((ROOT / f"{slug}.themes.json").read_text())["themes"]}
    # The model names its praise bucket differently per app ("praise", "Praise", "positive_feedback"): one key for all.
    praise_keys = {k for k, t in themes.items() if re.search(r"praise|positive", k + " " + t["label"], re.I)}
    for k in praise_keys:
        themes["praise"] = dict(themes.pop(k), key="praise")
    tags = {i: dict(v, themes=["praise" if k in praise_keys else k for k in v.get("themes", [])]) for i, v in tags.items()}
    rows = [dict(r, **tags.get(r["id"], {"themes": [], "bug": False, "gist": ""})) for r in rows if r["date"] >= meta["window_start"]]
    for r in rows:
        r["t"] = parse(r["date"])
    now = dt.datetime.now(dt.timezone.utc)
    # Quiet apps get a 12-month window instead of 90 days, so there is enough to rank (27 Nov 2026).
    days = 90 if sum(r["t"] >= now - dt.timedelta(days=90) for r in rows) >= 20 else 365
    recent_from, prior_from = now - dt.timedelta(days=days), now - dt.timedelta(days=2 * days)
    recent = [r for r in rows if r["t"] >= recent_from]
    prior = [r for r in rows if prior_from <= r["t"] < recent_from]

    # Themes
    th_out = []
    for key, t in themes.items():
        allr = [r for r in rows if key in r["themes"]]
        rec = [r for r in recent if key in r["themes"]]
        pri = [r for r in prior if key in r["themes"]]
        if not allr:
            continue
        th_out.append({
            "key": key, "label": t["label"], "describe": t["describe"],
            "n": len(allr), "n_recent": len(rec), "n_prior": len(pri),
            "low_recent": sum(r["rating"] <= 2 for r in rec),
            "pos_recent": sum(r["rating"] >= 4 for r in rec),
            "avg": round(statistics.mean(r["rating"] for r in allr), 2),
            "avg_recent": round(statistics.mean(r["rating"] for r in rec), 2) if rec else None,
            "bug_share": round(sum(r["bug"] for r in allr) / len(allr), 2),
            "last_seen": max(r["date"] for r in allr)[:10],
            "share_recent": round(len(rec) / len(recent), 3) if recent else 0,
            "quotes": quotes(rec or allr),
            "gists": [r["gist"] for r in sorted(rec or allr, key=lambda r: r["date"], reverse=True) if r["gist"] and r["rating"] <= 3][:25],
            "ids_recent": [r["id"] for r in rec],
        })
    th_out.sort(key=lambda x: (x["key"] == "praise", -x["low_recent"], -x["n_recent"]))  # problems = angry reviews first

    # Versions (in the order they first appeared)
    byv = collections.defaultdict(list)
    for r in rows:
        if r["version"]:
            byv[r["version"]].append(r)
    vers = []
    for v in sorted(byv, key=vkey):
        rs = byv[v]
        tc = collections.Counter(k for r in rs for k in r["themes"] if k != "praise")
        vers.append({"version": v, "n": len(rs), "avg": round(statistics.mean(r["rating"] for r in rs), 2),
                     "first": min(r["date"] for r in rs)[:10], "last": max(r["date"] for r in rs)[:10],
                     "bug_share": round(sum(r["bug"] for r in rs) / len(rs), 2),
                     "top": [themes[k]["label"] for k, _ in tc.most_common(2)]})
    prev = None
    for v in vers:
        v["delta"] = round(v["avg"] - prev["avg"], 2) if prev and v["n"] >= 5 and prev["n"] >= 5 else None
        v["flag"] = bool(v["delta"] is not None and v["delta"] <= -0.5 and v["n"] >= 8)
        if v["n"] >= 5:
            prev = v

    # Daily series + bursts
    day = collections.defaultdict(list)
    for r in rows:
        day[r["date"][:10]].append(r)
    first_day = min(r["t"] for r in rows).date()
    launch_quiet = first_day + dt.timedelta(days=7)  # launch week is busy by design, not a burst
    start = max((now - dt.timedelta(days=179)).date(), first_day)
    series = []
    for i in range((now.date() - start).days + 1):
        d = (start + dt.timedelta(days=i)).isoformat()
        rs = day.get(d, [])
        series.append({"d": d, "n": len(rs), "low": sum(r["rating"] <= 2 for r in rs)})
    base = statistics.median([s["n"] for s in series if s["d"] >= launch_quiet.isoformat()] or [0]) or 0.5
    bursts = []
    for s in series:
        if s["d"] >= launch_quiet.isoformat() and s["n"] >= max(6, base * 5):
            rs = sorted(day[s["d"]], key=lambda r: r["t"])
            tc = collections.Counter(k for r in rs for k in r["themes"] if k != "praise")
            top = tc.most_common(1)[0][0] if tc else None
            hits = [r for r in rs if top in r["themes"] and r["rating"] <= 3]
            # Apple's feed stamps every review in Pacific time (UTC-7); days are grouped on that same clock.
            timed = not rs[0].get("date_only")  # Shopify gives a date, not a time
            alert = (hits[2]["date"][11:16] + " Pacific" if len(hits) >= 3 else None) if timed else None
            vc = collections.Counter(r["version"] for r in rs).most_common(1)[0][0]
            bursts.append({"date": s["d"], "n": s["n"], "low": s["low"], "base": base,
                           "theme": themes[top]["label"] if top else None, "version": vc,
                           "first": rs[0]["date"][11:16] + " Pacific" if timed else None, "alert_at": alert,
                           "quotes": quotes(hits or rs, 3)})

    # Copy-paste / near-duplicate text across different reviews
    cand = [r for r in rows if len(r["body"]) >= 60]
    sh = [(r, shingles(r["body"])) for r in cand]
    dups = []
    for i in range(len(sh)):
        for j in range(i + 1, len(sh)):
            a, b = sh[i][1], sh[j][1]
            if not a or not b:
                continue
            jac = len(a & b) / len(a | b)
            if jac >= 0.6:
                dups.append({"jaccard": round(jac, 2), "a": {"date": sh[i][0]["date"][:10], "stars": sh[i][0]["rating"], "cc": sh[i][0]["cc"].upper(), "text": clip(sh[i][0]["body"], 140)},
                             "b": {"date": sh[j][0]["date"][:10], "stars": sh[j][0]["rating"], "cc": sh[j][0]["cc"].upper(), "text": clip(sh[j][0]["body"], 140)}})

    store = store_stats(meta)
    out = {
        "slug": slug, "name": meta["name"], "company": meta["company"], "store_kind": meta["store"], "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "window": {"from": min(r["date"] for r in rows)[:10], "to": now.date().isoformat(), "n": len(rows),
                   "recent_n": len(recent), "prior_n": len(prior), "recent_days": days,
                   "recent_label": "90 days" if days == 90 else "12 months", "countries": sorted({r["cc"].upper() for r in rows})},
        "store": store,
        "written_avg_recent": round(statistics.mean(r["rating"] for r in recent), 2) if recent else None,
        "bug_share_recent": round(sum(r["bug"] for r in recent) / len(recent), 2) if recent else None,
        "themes": th_out, "versions": vers[-14:], "series": series, "bursts": bursts, "dups": dups[:12],
    }
    (ROOT / f"{slug}.analysis.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{slug}: {len(rows)} reviews in window, {len(recent)} recent; {len(bursts)} bursts; {len(dups)} near-dups; "
          f"flags: {[v['version'] for v in vers if v['flag']]}")
    for t in th_out[:6]:
        print(f"  {t['label']}: recent {t['n_recent']} (prior {t['n_prior']}), low {t['low_recent']}, avg {t['avg_recent']}")


if __name__ == "__main__":
    for s in sys.argv[1:] or list(APPS):
        main(s)
