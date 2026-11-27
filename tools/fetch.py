#!/usr/bin/env python3
"""Pull public App Store reviews (Apple's customer-review RSS) for a set of apps.

Apple serves the most recent ~500 reviews per app per storefront (10 pages x 50).
We keep id, storefront, rating, version, date, title, body. No usernames are stored.
"""
import json, sys, time, urllib.request, pathlib

APPS = {
    "letterboxd": 1054271011,
    "serato-dj": 6754231707,
}
COUNTRIES = ["us", "gb", "ca", "au", "nz", "ie"]
OUT = pathlib.Path(__file__).resolve().parent.parent / "data"


def page(app_id, cc, n):
    url = f"https://itunes.apple.com/{cc}/rss/customerreviews/page={n}/id={app_id}/sortBy=mostRecent/json"
    req = urllib.request.Request(url, headers={"User-Agent": "review-radar/0.1"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r).get("feed", {}).get("entry", [])
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                print(f"  ! {cc} p{n}: {e}", file=sys.stderr)
                return []
            time.sleep(1.5 * (attempt + 1))


def main():
    for slug, app_id in APPS.items():
        seen, rows = set(), []
        for cc in COUNTRIES:
            got = 0
            for n in range(1, 11):
                entries = page(app_id, cc, n)
                if isinstance(entries, dict):
                    entries = [entries]
                fresh = [e for e in entries if "im:rating" in e]
                if not fresh:
                    break
                for e in fresh:
                    rid = e["id"]["label"]
                    if rid in seen:
                        continue
                    seen.add(rid)
                    rows.append({
                        "id": rid,
                        "cc": cc,
                        "rating": int(e["im:rating"]["label"]),
                        "version": e.get("im:version", {}).get("label", ""),
                        "date": e.get("updated", {}).get("label", ""),
                        "title": e.get("title", {}).get("label", ""),
                        "body": e.get("content", {}).get("label", ""),
                    })
                    got += 1
                time.sleep(0.3)
            print(f"{slug} {cc}: {got}")
        rows.sort(key=lambda r: r["date"], reverse=True)
        (OUT / f"{slug}.reviews.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
        print(f"{slug}: {len(rows)} reviews, {rows[-1]['date'][:10] if rows else '-'} .. {rows[0]['date'][:10] if rows else '-'}")


if __name__ == "__main__":
    main()
