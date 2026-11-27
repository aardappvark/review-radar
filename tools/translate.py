#!/usr/bin/env python3
"""Translate first, tap for the original (27 Nov 2026).

For every quote the page shows (problem evidence, incidents, copy-paste pairs, samples), a quick screen picks out text
that may not be English; the local model (gemma4) then names the language and translates it faithfully into English.
Quotes get lang / language / text_en / title_en; the page shows the English with "Translated from X · tap for original".
Also adds "other_languages" to each analysis: how many of the app's reviews the screen + model found in other
languages, by language, with up to six recent examples. Cached in data/translations.json (keyed by text hash).
Usage: translate.py [slug ...]
"""
import hashlib, json, re, sys, urllib.request, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
APPS = {a["slug"]: a for a in json.loads((ROOT / "apps.json").read_text())}
CACHE_PATH = DATA / "translations.json"
CACHE = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
EN = re.compile(r"\b(the|and|is|it|to|app|for|you|this|with|not|but|great|very|of|in|my|i|was|are|have)\b", re.I)
SYSTEM = ("You identify the language of an app review and translate it into English faithfully. Keep the meaning, tone and "
          "strength exactly: do not add, soften, strengthen, correct or explain anything. Keep app names, product names and "
          "numbers as written. Reply with JSON only: {\"lang\": \"<ISO 639-1 code>\", \"language\": \"<English name of the "
          "language>\", \"english\": \"<the translation>\"}. If the text is already English, lang is \"en\" and english repeats it.")


def maybe_foreign(t):
    if re.search(r"[^\x00-ɏ -⁯€™←-⇿☀-➿\U0001F000-\U0001FAFF]", t):
        return True
    w = re.findall(r"[A-Za-zÀ-ÿ']+", t)
    return len(w) >= 3 and len(EN.findall(t)) / max(len(w), 1) < 0.10


def ask(text):
    k = hashlib.sha256(text.encode()).hexdigest()[:24]
    if k in CACHE:
        return CACHE[k]
    body = json.dumps({"model": "gemma4:latest", "stream": False, "think": False, "format": "json", "options": {"temperature": 0},
                       "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text[:1500]}]}).encode()
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/chat", body, {"Content-Type": "application/json"}), timeout=180))
        j = json.loads(r["message"]["content"])
        res = {"lang": str(j.get("lang", "")).lower()[:5], "language": str(j.get("language", ""))[:30], "english": str(j.get("english", "")).strip()}
    except Exception:  # noqa: BLE001
        return None
    if res["lang"] and res["lang"] != "en" and (not res["english"] or res["english"].strip() == text.strip()):
        return None   # a "translation" identical to the source is not a translation
    CACHE[k] = res
    return res


def translate_quote(q, text_key="text"):
    src = (q.get("title", "") + " " + q.get(text_key, "")).strip()
    if not src or not maybe_foreign(src):
        return False
    res = ask(q[text_key]) if q.get(text_key) else None
    if not res or res["lang"] == "en":
        return False
    q["lang"], q["language"], q["text_en"] = res["lang"], res["language"], res["english"]
    if q.get("title"):
        t = ask(q["title"])
        if t and t["lang"] != "en":
            q["title_en"] = t["english"]
    return True


def main(slug):
    path = DATA / f"{slug}.analysis.json"
    a = json.loads(path.read_text())
    n = 0
    for t in a.get("themes", []):
        for q in t.get("quotes", []):
            n += translate_quote(q)
    for b in a.get("bursts", []):
        for q in b.get("quotes", []):
            n += translate_quote(q)
    for d in a.get("dups", []):
        for side in ("a", "b"):
            n += translate_quote(d[side])
    for q in a.get("sample", []) or []:
        n += translate_quote(q)
    other = {"count": 0, "of": 0, "by_language": {}, "examples": []}
    rp = DATA / f"{slug}.reviews.json"
    if rp.exists() and not a.get("sample_only"):
        start = APPS[slug]["window_start"]
        rows = [r for r in json.loads(rp.read_text()) if r["date"] >= start and r["body"].strip()]
        other["of"] = len(rows)
        found = []
        for r in rows:
            if not maybe_foreign(r.get("title", "") + " " + r["body"]):
                continue
            res = ask(r["body"])
            if res and res["lang"] != "en":
                found.append((r, res))
        other["count"] = len(found)
        for r, res in found:
            other["by_language"][res["language"] or res["lang"]] = other["by_language"].get(res["language"] or res["lang"], 0) + 1
        for r, res in sorted(found, key=lambda x: x[0]["date"], reverse=True)[:6]:
            title_res = ask(r["title"]) if r.get("title") else None
            other["examples"].append({"stars": r["rating"], "date": r["date"][:10], "cc": r["cc"], "lang": res["lang"], "language": res["language"],
                                      "title": r.get("title", ""), "title_en": title_res["english"] if title_res and title_res["lang"] != "en" else "",
                                      "text": r["body"][:600], "text_en": res["english"][:700]})
    a["other_languages"] = other
    path.write_text(json.dumps(a, ensure_ascii=False, indent=1))
    CACHE_PATH.write_text(json.dumps(CACHE, ensure_ascii=False))
    print(f"{slug}: {n} quotes translated; {other['count']} of {other['of']} reviews in other languages {other['by_language']}")


if __name__ == "__main__":
    for s in sys.argv[1:] or list(APPS):
        if (DATA / f"{s}.analysis.json").exists():
            main(s)
