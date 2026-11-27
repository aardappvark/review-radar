#!/usr/bin/env python3
"""Pull public reviews for every app in apps.json.

- Apple: the customer-review RSS feed, the most recent ~500 per storefront (10 pages x 50), six English storefronts.
- Shopify App Store: the public review pages (newest first, 10 per page), up to MAX_SHOPIFY_PAGES pages.
We keep id, country, rating, version, date, title and text. Reviewer and store names are never stored.
Usage: fetch.py [slug ...]   (no slugs = all apps)
"""
import datetime as dt, html, json, re, sys, time, urllib.request, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data"
APPS = {a["slug"]: a for a in json.loads((ROOT / "apps.json").read_text())}
COUNTRIES = ["us", "gb", "ca", "au", "nz", "ie"]
MAX_SHOPIFY_PAGES = 50
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) review-radar/0.2"}


def get(url, as_json=False):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
                body = r.read()
                return json.loads(body) if as_json else body.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                print(f"  ! {url[:90]}: {e}", file=sys.stderr)
                return None
            time.sleep(2 * (attempt + 1))


def apple(app, countries=None, pages=10):
    seen, rows = set(), []
    for cc in countries or COUNTRIES:
        got = 0
        for n in range(1, pages + 1):
            d = get(f"https://itunes.apple.com/{cc}/rss/customerreviews/page={n}/id={app['id']}/sortBy=mostRecent/json", as_json=True)
            entries = (d or {}).get("feed", {}).get("entry", [])
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
                rows.append({"id": rid, "cc": cc, "rating": int(e["im:rating"]["label"]),
                             "version": e.get("im:version", {}).get("label", ""), "date": e.get("updated", {}).get("label", ""),
                             "title": e.get("title", {}).get("label", ""), "body": e.get("content", {}).get("label", "")})
                got += 1
            time.sleep(0.3)
        print(f"  {app['slug']} {cc}: {got}")
    return rows


# Apple's storefront ids for the iTunes review endpoint (X-Apple-Store-Front).
STOREFRONT = {"us": 143441, "gb": 143444, "ca": 143455, "au": 143460, "nz": 143461, "ie": 143449, "br": 143503, "de": 143443,
              "fr": 143442, "es": 143454, "mx": 143468, "it": 143450, "jp": 143462, "nl": 143452, "se": 143456, "pl": 143478,
              "tr": 143480, "kr": 143466}


def itunes(app, countries=None, max_per_country=500, since=None):
    """The iTunes store's own review endpoint (the RSS feed went empty on 27 Nov 2026). 50 per request, newest first,
    with developer responses; no app version. Reviewer names are dropped."""
    rows, seen = [], set()
    hdr = {"User-Agent": "iTunes/12.12.10 (Macintosh; OS X 13.6) AppleWebKit/7616.1.27.211.1"}
    for cc in countries or COUNTRIES:
        got, start = 0, 0
        while start < max_per_country:
            url = (f"https://itunes.apple.com/WebObjects/MZStore.woa/wa/userReviewsRow?id={app['id']}&displayable-kind=11"
                   f"&startIndex={start}&endIndex={start + 50}&sort=0&appVersion=all")
            batch = []
            for attempt in range(3):
                try:
                    req = urllib.request.Request(url, headers=dict(hdr, **{"X-Apple-Store-Front": f"{STOREFRONT[cc]},29"}))
                    with urllib.request.urlopen(req, timeout=25) as r:
                        batch = json.load(r).get("userReviewList", [])
                    break
                except Exception as e:  # noqa: BLE001
                    if attempt == 2:
                        print(f"  ! {app['slug']} {cc} @{start}: {e}", file=sys.stderr)
                    time.sleep(2 * (attempt + 1))
            for x in batch:
                rid = str(x.get("userReviewId"))
                if rid in seen:
                    continue
                seen.add(rid)
                rows.append({"id": rid, "cc": cc, "rating": int(x.get("rating", 0)), "version": "", "date": x.get("date", ""),
                             "title": x.get("title", "") or "", "body": x.get("body", "") or "", "replied": bool(x.get("developerResponse"))})
                got += 1
            time.sleep(1.0)
            if len(batch) < 50 or (since and batch and batch[-1].get("date", "") < since):
                break
            start += 50
        print(f"  {app['slug']} {cc}: {got}")
    return rows


def shopify(app):
    rows, seen = [], set()
    for n in range(1, MAX_SHOPIFY_PAGES + 1):
        h = get(f"https://apps.shopify.com/{app['id']}/reviews?sort_by=newest&page={n}")
        if not h:
            break
        blocks = re.split(r'<div data-merchant-review="" data-review-content-id="', h)[1:]
        if not blocks:
            break
        for b in blocks:
            rid = b.split('"', 1)[0]
            if rid in seen:
                continue
            seen.add(rid)
            stars = re.search(r'aria-label="(\d) out of 5 stars"', b)
            # A developer reply is a separate block inside the review: cut it off before reading the merchant's text.
            main = re.split(r'(?i)replied|<div[^>]*data-reply', b)[0]
            main = re.sub(r"<svg.*?</svg>", "", main, flags=re.S)
            parts = [html.unescape(p).strip() for p in re.split(r"<[^>]+>", main)]
            parts = [p for p in parts if p and not p.startswith(("tw-", "class=")) and p not in ("Show more", "Show less")]
            date_i = next((i for i, p in enumerate(parts) if re.fullmatch(r"[A-Z][a-z]+ \d{1,2}, \d{4}", p)), None)
            if date_i is None or not stars:
                continue
            d = dt.datetime.strptime(parts[date_i], "%B %d, %Y").date().isoformat()
            # Layout after the date: text paragraph(s), store name (dropped), country, "N years using the app".
            u = next((i for i in range(date_i + 1, len(parts)) if "using the app" in parts[i]), None)
            if u is not None and u - 2 > date_i:
                text, country = "\n".join(parts[date_i + 1:u - 2]), parts[u - 1]
            else:  # layout not recognised: keep the stars only, so a store name can never be stored as text
                text, country = "", ""
            rows.append({"id": rid, "cc": country, "rating": int(stars.group(1)), "version": "",
                         "date": f"{d}T12:00:00-07:00", "date_only": True, "title": "", "body": text,
                         "replied": bool(re.search(r'data-reply-id="\d+"', b))})  # the publisher answered publicly
        time.sleep(1.0)
    print(f"  {app['slug']}: {len(rows)} reviews from {n} pages")
    return rows


def main():
    if sys.argv[1:2] == ["--intl"]:
        # International storefronts (apps.json "intl_countries"): the 100 most recent per country, kept apart from the
        # English-storefront analysis so its published figures don't move. Feeds the "Around the world" section.
        for slug in sys.argv[2:]:
            app = APPS[slug]
            rows = itunes(app, app.get("intl_countries", []), max_per_country=100)
            rows.sort(key=lambda r: r["date"], reverse=True)
            (OUT / f"{slug}.intl.reviews.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
            print(f"{slug} (international): {len(rows)} reviews from {len(app.get('intl_countries', []))} storefronts")
        return
    for slug in sys.argv[1:] or list(APPS):
        app = APPS[slug]
        if app["store"] == "shopify":
            rows = shopify(app)
        elif app.get("source") == "itunes":
            rows = itunes(app, since=app.get("window_start"))
        else:
            rows = apple(app)
        rows.sort(key=lambda r: r["date"], reverse=True)
        (OUT / f"{slug}.reviews.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
        print(f"{slug}: {len(rows)} reviews, {rows[-1]['date'][:10] if rows else '-'} .. {rows[0]['date'][:10] if rows else '-'}")


if __name__ == "__main__":
    main()
