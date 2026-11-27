#!/usr/bin/env python3
"""A sample, not an analysis: the reviews Apple's own App Store web page shows (about 10, chosen by Apple, some years old).

Used while Apple's customer-review feed returns empty lists (from 27 Nov 2026). Writes data/<slug>.analysis.json in the
same shape as analyse.py with sample_only=True: store rating, the sampled reviews, no ranking, no themes, no incidents.
Reviewer names are never stored; developer responses are kept apart from the review text.
Usage: sample.py befunky visionn
"""
import datetime as dt, html, json, re, sys, urllib.request, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
APPS = {a["slug"]: a for a in json.loads((ROOT / "apps.json").read_text())}
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15"}


def text_of(fragment):
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment)).strip()


def sample(app):
    lookup = json.load(urllib.request.urlopen(urllib.request.Request(f"https://itunes.apple.com/lookup?id={app['id']}&country=us", headers=UA), timeout=20))["results"][0]
    page_url = lookup["trackViewUrl"].split("?")[0] + "?see-all=reviews"
    h = urllib.request.urlopen(urllib.request.Request(page_url, headers=UA), timeout=30).read().decode("utf-8", "replace")
    out = []
    for b in re.split(r'<div class="container svelte-[a-z0-9]+" aria-labelledby="review-', h)[1:]:
        b = b.split("<dialog", 1)[0]  # the "read more" dialog repeats the text
        rid = b.split("-", 1)[0]
        title = re.search(r'<h3 id="review-\d+-title"[^>]*>(.*?)</h3>', b, re.S)
        stars = re.search(r'aria-label="(\d) Stars?"', b)
        when = re.search(r'<time[^>]*datetime="([^"]+)"', b)
        bodies = re.findall(r"<!-- HTML_TAG_START -->(.*?)<!-- HTML_TAG_END -->", b, re.S)
        if not (title and stars and when and bodies):
            continue
        reply = text_of(bodies[1]) if len(bodies) > 1 else ""
        out.append({"id": rid, "stars": int(stars.group(1)), "date": when.group(1)[:10], "title": text_of(title.group(1)),
                    "text": text_of(bodies[0]), "developer_replied": bool(reply)})
    return lookup, page_url, out


def main(slugs):
    for slug in slugs:
        app = APPS[slug]
        lk, url, rows = sample(app)
        avg = round(sum(r["stars"] for r in rows) / len(rows), 2) if rows else None
        a = {
            "slug": slug, "name": app["name"], "company": app["company"], "store_kind": "apple", "sample_only": True,
            "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "window": {"from": min((r["date"] for r in rows), default=""), "to": max((r["date"] for r in rows), default=""),
                       "n": len(rows), "recent_n": len(rows), "prior_n": 0, "countries": ["US"], "recent_days": 0, "recent_label": "sample"},
            "store": {"avg": round(lk["averageUserRating"], 2), "count": lk["userRatingCount"], "version": lk["version"],
                      "version_date": lk["currentVersionReleaseDate"][:10], "released": lk["releaseDate"][:10], "store": "apple", "url": url.split("?")[0]},
            "written_avg_recent": avg, "bug_share_recent": None,
            "sample": rows, "sample_note": "These are the reviews Apple shows on the App Store page: chosen by Apple, some years old. "
                       "Apple's review feed has returned empty lists for every app since 27 Nov 2026, so this app gets the full analysis when it returns.",
            "themes": [], "versions": [], "series": [], "bursts": [], "dups": [],
        }
        (DATA / f"{slug}.analysis.json").write_text(json.dumps(a, ensure_ascii=False, indent=1))
        print(f"{slug}: {len(rows)} sampled reviews, {a['window']['from']} .. {a['window']['to']}, store {a['store']['avg']} ({a['store']['count']})")


if __name__ == "__main__":
    main(sys.argv[1:] or ["befunky", "visionn"])
