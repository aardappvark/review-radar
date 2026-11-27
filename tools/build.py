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
    top = next((t for t in a["themes"] if t["key"] != "praise"), None)
    if a["bursts"]:
        b = max(a["bursts"], key=lambda x: x["n"])
        return (f"The store shows <b>{a['store']['avg']:.2f}★</b>; people who take the time to write average "
                f"<b>{a['written_avg_recent']:.2f}★</b>. The loudest day in six months was <b>{mdate(b['date'])}</b>: "
                f"{b['n']} reviews in one day on v{b['version']}, mostly <b>{b['theme']}</b>"
                + (f", and a three-report alert would have fired at <b>{b['alert_at']}</b>." if b["alert_at"] else "."))
    return (f"Launched {mdate(a['store']['released'])}. The store shows <b>{a['store']['avg']:.2f}★</b>; written reviews average "
            f"<b>{a['written_avg_recent']:.2f}★</b>. The biggest complaint is <b>{top['label']}</b>: "
            f"{top['n_recent']} of {a['window']['recent_n']} reviews, {top['low_recent']} of them at 1–2★.")


def main():
    apps = []
    for slug in (sys.argv[1:] or META["apps"]):
        a = json.loads((DATA / f"{slug}.analysis.json").read_text())
        a["callout"] = callout(a)
        for t in a["themes"]:
            t.pop("gists", None)
            t.pop("ids_recent", None)
        apps.append(a)
    data = {"apps": apps, "meta": META}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = (ROOT / "site" / "template.html").read_text().replace("__DATA__", blob)
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "index.html").write_text(html)  # GitHub Pages serves /docs
    print(f"docs/index.html {len(html) // 1024} KB, apps: {[a['name'] for a in apps]}")


if __name__ == "__main__":
    main()
