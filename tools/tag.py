#!/usr/bin/env python3
"""Tag reviews with a local model (Ollama gemma4, think:false). Free, private, cached.

Step 1 (discover): the model reads a sample of low-star reviews and proposes a theme list.
Step 2 (classify): every review gets 0-2 themes, a bug flag and a one-line gist.
Cache: data/<slug>.tags.json keyed by review id, so reruns only tag new reviews.
"""
import json, sys, pathlib, random, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent / "data"
MODEL = "gemma4:latest"
BATCH = 8


def ask(prompt, num_predict=1500):
    body = json.dumps({"model": MODEL, "prompt": prompt, "stream": False, "think": False,
                       "format": "json", "options": {"temperature": 0, "num_predict": num_predict}}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(json.load(r)["response"])


def discover(slug, app_name, rows):
    path = ROOT / f"{slug}.themes.json"
    if path.exists():
        return json.loads(path.read_text())
    low = [r for r in rows if r["rating"] <= 3]
    random.Random(7).shuffle(low)
    sample = "\n".join(f"- [{r['rating']}*] {(r['title'] + ': ') if r['title'] else ''}{r['body'][:300]}" for r in low[:120] if r['body'].strip())
    out = ask(f"""You are a product analyst reading public reviews of the {app_name} app.
Propose 8 to 11 distinct, specific complaint/request themes that cover these reviews.
Use short plain labels a product manager would use (e.g. "Login & account", "Crashes on launch").
Also include one theme named "Praise" for purely positive reviews.
Return JSON: {{"themes": [{{"key": "snake_case", "label": "...", "describe": "one sentence"}}]}}

Reviews:
{sample}""", 2000)
    path.write_text(json.dumps(out, indent=1))
    return out


def classify(slug, app_name, rows, themes):
    path = ROOT / f"{slug}.tags.json"
    cache = json.loads(path.read_text()) if path.exists() else {}
    keys = [t["key"] for t in themes["themes"]]
    menu = "\n".join(f"- {t['key']}: {t['describe']}" for t in themes["themes"])
    todo = [r for r in rows if r["id"] not in cache and (r["body"].strip() or r["title"].strip())]  # stars-only reviews have nothing to tag
    print(f"{slug}: {len(todo)} to tag ({len(cache)} cached)")
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        listing = "\n".join(f"#{j} [{r['rating']}*{', v' + r['version'] if r['version'] else ''}] {(r['title'] + ': ') if r['title'] else ''}{r['body'][:600]}" for j, r in enumerate(chunk))
        try:
            out = ask(f"""Classify each public review of the {app_name} app.
Themes (use only these keys):
{menu}

For each review return: n (its # number), themes (0-2 keys, most important first),
bug (true only if it reports something broken: crash, error, data loss, feature not working),
gist (max 12 words, neutral, what the reviewer wants or reports; no quotes).
Return JSON: {{"items": [{{"n": 0, "themes": ["key"], "bug": false, "gist": "..."}}]}}

Reviews:
{listing}""")
        except Exception as e:  # noqa: BLE001
            print("  ! batch failed:", e, file=sys.stderr)
            continue
        for it in out.get("items", []):
            try:
                r = chunk[int(it["n"])]
            except (KeyError, ValueError, IndexError, TypeError):
                continue
            cache[r["id"]] = {
                "themes": [k for k in it.get("themes", []) if k in keys][:2],
                "bug": bool(it.get("bug")),
                "gist": str(it.get("gist", ""))[:120],
            }
        if (i // BATCH) % 10 == 0:
            path.write_text(json.dumps(cache, ensure_ascii=False))
            print(f"  {min(i + BATCH, len(todo))}/{len(todo)}", flush=True)
    path.write_text(json.dumps(cache, ensure_ascii=False))
    missing = [r["id"] for r in rows if r["id"] not in cache and (r["body"].strip() or r["title"].strip())]
    print(f"{slug}: tagged {len(rows) - len(missing)}/{len(rows)}")


_APPS = json.loads((ROOT.parent / "apps.json").read_text())
APPS = {a["slug"]: f"{a['name']} {'iOS' if a['store'] == 'apple' else 'Shopify'}" for a in _APPS}  # e.g. "Letterboxd iOS"

if __name__ == "__main__":
    intl = sys.argv[1:2] == ["--intl"]   # tag the international reviews with the app's existing theme list
    only = (sys.argv[2:] if intl else sys.argv[1:]) or list(APPS)
    for slug in only:
        if intl:
            rows = json.loads((ROOT / f"{slug}.intl.reviews.json").read_text())
            th = json.loads((ROOT / f"{slug}.themes.json").read_text())
            classify(f"{slug}.intl", APPS[slug], rows, th)
            continue
        rows = json.loads((ROOT / f"{slug}.reviews.json").read_text())
        th = discover(slug, APPS[slug], rows)
        print(json.dumps([t["label"] for t in th["themes"]]))
        classify(slug, APPS[slug], rows, th)
