#!/usr/bin/env python3
"""Around the world: an app's reviews in other countries' App Stores, kept apart from its English-storefront analysis.

Reads data/<slug>.intl.reviews.json (fetch.py --intl) and data/<slug>.intl.tags.json (tag.py --intl, the app's own
theme list) and adds "world" to data/<slug>.analysis.json: per country, reviews read, average stars, share at 1-2 stars,
and the top complaint; plus up to two recent low-star examples per language, translated by the local model, for the
page's "tap for original". Usage: world.py letterboxd
"""
import collections, json, statistics, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT / "tools"))
import translate  # noqa: E402  (same model, prompt and cache as the quote translations)

NAMES = {"br": "Brazil", "de": "Germany", "fr": "France", "es": "Spain", "mx": "Mexico", "it": "Italy", "jp": "Japan",
         "nl": "Netherlands", "se": "Sweden", "pl": "Poland", "tr": "Türkiye", "kr": "South Korea", "us": "United States"}


def main(slug):
    path = DATA / f"{slug}.analysis.json"
    a = json.loads(path.read_text())
    rows = json.loads((DATA / f"{slug}.intl.reviews.json").read_text())
    tags = json.loads((DATA / f"{slug}.intl.tags.json").read_text())
    themes = {t["key"]: t["label"] for t in json.loads((DATA / f"{slug}.themes.json").read_text())["themes"]}
    praise = {k for k, l in themes.items() if "praise" in (k + l).lower() or "positive" in (k + l).lower()}
    by = collections.defaultdict(list)
    for r in rows:
        by[r["cc"]].append(r)
    countries = []
    for cc, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        tc = collections.Counter(k for r in rs if r["rating"] <= 2 for k in tags.get(r["id"], {}).get("themes", []) if k not in praise)
        top = tc.most_common(1)
        countries.append({"cc": cc, "country": NAMES.get(cc, cc.upper()), "n": len(rs),
                          "avg": round(statistics.mean(r["rating"] for r in rs), 2),
                          "low_share": round(sum(r["rating"] <= 2 for r in rs) / len(rs), 3),
                          "top_complaint": themes.get(top[0][0]) if top else None, "top_n": top[0][1] if top else 0,
                          "since": min(r["date"] for r in rs)[:10]})
    examples, per_lang = [], collections.Counter()
    for r in sorted(rows, key=lambda r: r["date"], reverse=True):
        if r["rating"] > 2 or not r["body"].strip() or len(examples) >= 10:
            continue
        res = translate.ask(r["body"])
        if not res or res["lang"] == "en" or per_lang[res["lang"]] >= 2:
            continue
        t = translate.ask(r["title"]) if r.get("title") else None
        per_lang[res["lang"]] += 1
        examples.append({"stars": r["rating"], "date": r["date"][:10], "cc": NAMES.get(r["cc"], r["cc"]), "lang": res["lang"],
                         "language": res["language"], "title": r.get("title", ""),
                         "title_en": t["english"] if t and t["lang"] != "en" else "", "text": r["body"][:600], "text_en": res["english"][:700]})
    a["world"] = {"countries": countries, "n": len(rows), "examples": examples,
                  "note": "The most recent reviews (up to 100) in each country's App Store, read through the iTunes store's review endpoint "
                          "and tagged with the same themes as the English analysis above, which they don't change."}
    path.write_text(json.dumps(a, ensure_ascii=False, indent=1))
    translate.CACHE_PATH.write_text(json.dumps(translate.CACHE, ensure_ascii=False))
    for c in countries:
        print(f"{slug} {c['country']:12} {c['n']:3} reviews, avg {c['avg']}, 1-2 star {c['low_share']:.0%}, top complaint {c['top_complaint']} ({c['top_n']})")
    print(f"{len(examples)} translated examples: {dict(per_lang)}")


if __name__ == "__main__":
    for s in sys.argv[1:] or ["letterboxd"]:
        main(s)
