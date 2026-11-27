#!/usr/bin/env python3
"""Did the fix work? For each complaint theme, its share of written reviews release by release.

Adds "fixes" to data/<slug>.analysis.json (App Store apps only: Shopify reviews carry no version). A theme is tracked
when it peaks at 10%+ of a release's reviews with at least 5 mentions. The verdict is read from the numbers only:
  "fell after vX"   - every later release (5+ reviews) sits at a third of the peak or less;
  "still open"      - the newest release is at half the peak or more;
  "easing"          - anything in between;
  "early"           - fewer than 15 reviews since the spike: too early to tell.
The spike tracked is the most recent release with 5+ mentions and 10%+ of reviews.
It describes what reviews say, not why: a drop after a release is consistent with a fix, not proof of one.
Run after analyse.py and brief.py (it only adds a field). Usage: fixes.py [slug ...]
"""
import collections, json, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
APPS = {a["slug"]: a for a in json.loads((ROOT / "apps.json").read_text())}
MIN_REVIEWS = 5


def vkey(v):
    return [int(p) if p.isdigit() else 0 for p in v.split(".")]


def main(slug):
    meta = APPS[slug]
    path = DATA / f"{slug}.analysis.json"
    a = json.loads(path.read_text())
    if meta["store"] != "apple" or a.get("sample_only"):
        a["fixes"] = []
        path.write_text(json.dumps(a, ensure_ascii=False, indent=1))
        return
    reviews = [r for r in json.loads((DATA / f"{slug}.reviews.json").read_text()) if r["date"] >= meta["window_start"] and r["version"]]
    tags = json.loads((DATA / f"{slug}.tags.json").read_text())
    labels = {t["key"]: t["label"] for t in a["themes"]}
    themes = json.loads((DATA / f"{slug}.themes.json").read_text())["themes"]
    raw_label = {t["key"]: t["label"] for t in themes}
    praise = {k for k, l in raw_label.items() if "praise" in (k + l).lower() or "positive" in (k + l).lower()}

    per_v = collections.defaultdict(lambda: {"n": 0, "hits": collections.Counter()})
    for r in reviews:
        v = per_v[r["version"]]
        v["n"] += 1
        for k in tags.get(r["id"], {}).get("themes", []):
            v["hits"][k] += 1
    versions = sorted((v for v in per_v if per_v[v]["n"] >= MIN_REVIEWS), key=vkey)

    happy = {t["key"] for t in a["themes"] if t.get("pos_recent", 0) >= 2 * max(t.get("low_recent", 0), 1)}
    out = []
    for k in raw_label:
        if k in praise or k in happy:   # requests from happy reviewers aren't something a fix "works" on
            continue
        series = [{"version": v, "n": per_v[v]["n"], "hits": per_v[v]["hits"][k],
                   "share": round(per_v[v]["hits"][k] / per_v[v]["n"], 3)} for v in versions]
        if not series:
            continue
        # The most recent spike (not the all-time high, which is often a tiny old release).
        spikes = [x for x in series if x["hits"] >= 5 and x["share"] >= 0.10]
        if not spikes:
            continue
        peak = spikes[-1]
        later = series[series.index(peak) + 1:]
        if sum(x["n"] for x in later) < 15:
            verdict, after = "early", None          # not enough reviews since the spike to say anything
        elif all(x["share"] <= peak["share"] / 3 for x in later):
            verdict, after = "fell", later[0]["version"]
        elif series[-1]["share"] >= peak["share"] / 2:
            verdict, after = "open", None
        else:
            verdict, after = "easing", None
        out.append({"key": k, "label": labels.get(k, raw_label[k]), "peak": peak, "verdict": verdict, "after": after,
                    "latest": series[-1], "series": series[-12:]})
    out.sort(key=lambda f: (f["verdict"] != "fell", -f["peak"]["share"]))   # the evidence of a fix first
    a["fixes"] = out[:4]
    path.write_text(json.dumps(a, ensure_ascii=False, indent=1))
    for f in a["fixes"]:
        print(f"{slug}: {f['label']}: peak {f['peak']['share']:.0%} on v{f['peak']['version']} ({f['peak']['hits']}/{f['peak']['n']}), "
              f"verdict {f['verdict']}{' after v' + f['after'] if f['after'] else ''}; latest v{f['latest']['version']} {f['latest']['share']:.0%}")


if __name__ == "__main__":
    for s in sys.argv[1:] or list(APPS):
        if (DATA / f"{s}.analysis.json").exists():
            main(s)
