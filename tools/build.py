#!/usr/bin/env python3
"""Inject the analysis into site/template.html -> site/index.html (one self-contained file)."""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
META = json.loads((ROOT / "site" / "meta.json").read_text())


def mdate(d):
    import datetime as dt
    return dt.date.fromisoformat(d).strftime("%-d %b")


def callout(a):
    gap = a["store"]["avg"] - a["written_avg_recent"]
    top = next((t for t in a["themes"] if t["key"] != "praise" and t["n_recent"] > 0), None)
    happy = lambda t: t.get("pos_recent", 0) >= 2 * max(t["low_recent"], 1)   # raised mostly in 4-5 star reviews
    angry = next((t for t in a["themes"] if t["key"] != "praise" and t["low_recent"] > 0 and not happy(t)), None)
    if a["bursts"]:
        b = max(a["bursts"], key=lambda x: x["n"])
        return (f"The store shows <b>{a['store']['avg']:.2f}★</b>; people who take the time to write average "
                f"<b>{a['written_avg_recent']:.2f}★</b>. The loudest day in six months was <b>{mdate(b['date'])}</b>: "
                f"{b['n']} reviews in one day{' on v' + b['version'] if b.get('version') else ''}, mostly <b>{b['theme']}</b>"
                + (f", and a three-report alert would have fired at <b>{b['alert_at']}</b>." if b["alert_at"] else "."))
    import datetime as _d
    rel = a["store"].get("released")
    lead = f"Launched {mdate(rel)}. " if rel and (_d.date.today() - _d.date.fromisoformat(rel)).days < 120 else ""
    where = "The Shopify App Store shows" if a.get("store_kind") == "shopify" else "The store shows"
    L = a["window"].get("recent_label", "90 days")
    s = (f"{lead}{where} <b>{a['store']['avg']:.2f}★</b>; written reviews in the last {L} average <b>{a['written_avg_recent']:.2f}★</b>.")
    if angry:
        s += f" The biggest complaint is <b>{angry['label']}</b>: {angry['n_recent']} of {a['window']['recent_n']} reviews, {angry['low_recent']} of them at 1–2★."
        if top and top is not angry and happy(top):
            s += f" The most-mentioned theme, <b>{top['label']}</b>, comes up mostly in happy reviews."
    elif top:
        s += f" Nothing draws real anger: the most-raised theme is <b>{top['label']}</b> ({top['n_recent']} reviews), mostly requests."
    elif a["window"]["recent_n"]:
        k = a['window']['recent_n']
        s += f" {'The one written review' if k == 1 else f'The {k} written reviews'} in that time {'is' if k == 1 else 'are'} praise: nothing to fix here, which is worth knowing too."
    else:
        s += f" No written reviews in the last {L}; the analysis below covers the {a['window']['n']} since {mdate(a['window']['from'])}."
    return s


def main():
    apps = []
    listed = {x["slug"]: x for x in json.loads((ROOT / "apps.json").read_text())}
    for slug in (sys.argv[1:] or [s for s in listed if (DATA / f"{s}.analysis.json").exists() and s in META["apps"]]):
        a = json.loads((DATA / f"{slug}.analysis.json").read_text())
        a["tab"] = listed.get(slug, {}).get("tab", a["name"])
        a["callout"] = callout(a)
        for t in a["themes"]:
            t.pop("gists", None)
            t.pop("ids_recent", None)
        apps.append(a)
    # Data for agents (the MCP server reads these): one file per app plus an index.
    (ROOT / "docs" / "data").mkdir(parents=True, exist_ok=True)
    index = []
    for a in apps:
        (ROOT / "docs" / "data" / f"{a['slug']}.json").write_text(json.dumps(a, ensure_ascii=False))
        index.append({"slug": a["slug"], "app": a["name"], "company": a.get("company"), "store": a.get("store_kind"),
                      "store_rating": a["store"]["avg"], "store_rating_count": a["store"]["count"],
                      "written_reviews_read": a["window"]["n"], "window": f"last {a['window'].get('recent_label', '90 days')}",
                      "problems_ranked": sum(1 for t in a["themes"] if t.get("brief")), "incidents": len(a["bursts"])})
    import datetime as _dt
    (ROOT / "docs" / "data" / "index.json").write_text(json.dumps({"generated": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "apps": index}, ensure_ascii=False, indent=1))
    data = {"apps": apps, "meta": META}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = (ROOT / "site" / "template.html").read_text().replace("__DATA__", blob)
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "index.html").write_text(html)  # GitHub Pages serves /docs
    print(f"docs/index.html {len(html) // 1024} KB, apps: {[a['name'] for a in apps]}")


if __name__ == "__main__":
    main()
