#!/usr/bin/env python3
"""Action points for each major problem: real, specific asks versus noise, then a direction and an outcome.

For every problem card, the local model reads the reviews that raise it (last window) and sorts them:
  SPECIFIC = names something a team could act on (a named feature, screen, behaviour, device, design system, price, bug)
  NOISE    = a general feeling with nothing to act on ("bad UI", "hate the update", "needs work")
It groups the specific ones into concrete requests. The CODE does all counting (from the review ids the model returns),
so every number on the page is computed, not written by the model. A second call turns the top requests into a
direction, an expected outcome and how to check it; any number it writes must be one of the computed counts.
Adds theme["actions"]. Usage: actions.py [slug ...]
"""
import json, re, sys, pathlib, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
APPS = {a["slug"]: a for a in json.loads((ROOT / "apps.json").read_text())}
MODEL = "gemma4:26b"
SKIP = re.compile(r"\b(israel|palestin|gaza|trump|biden|woke|nazi|fuck|shit|gaf|wtf|damn|bitch|idiot|retard|garbage|stupid|hate)\w*", re.I)


def ask(system, user, num_predict=1400):
    body = json.dumps({"model": MODEL, "stream": False, "think": False, "format": "json", "options": {"temperature": 0.1, "num_predict": num_predict},
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
    with urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/chat", body, {"Content-Type": "application/json"}), timeout=900) as r:
        return json.loads(json.load(r)["message"]["content"])


def clip(t, n=170):
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " …"


STOP = set("the a an to of and or for in on with from app apps add fix allow stop make more less use using user users when into its it be is are".split())


def words(t):
    out = set()
    for w in re.findall(r"[a-z0-9]+", t.lower()):
        if len(w) < 2 or w in STOP:
            continue
        out.add(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w)   # shows ~ show
    return out


def snippet(text, rw, n=170):
    """Quote the sentence that carries the ask, not just the opening of a long review."""
    text = re.sub(r"\s+", " ", text).strip()
    sents = re.split(r"(?<=[.!?])\s+", text)
    k = max(range(len(sents)), key=lambda j: (len(rw & words(sents[j])), -j))
    if k == 0 or not (rw & words(sents[k])):
        return clip(text, n)
    return "… " + clip(" ".join(sents[k:]), n)


def best_quote(request, cands):
    """The review that shares the most words with the request (so the quote shows the ask), skipping unsafe text."""
    rw = words(request)
    ok = [r for r in cands if not SKIP.search(r["body"] + " " + r.get("title", ""))]
    return max(ok, key=lambda r: (len(rw & words(snippet(r["body"], rw))), r["rating"] <= 2, -len(r["body"])), default=None)   # ties: the shortest, most focused review


def names_top(direction, top):
    """The direction's first sentence must name the most-asked request (or an equally asked one)."""
    first = re.split(r"(?<=[.!?])\s+", direction.strip())[0]
    return len(words(first) & words(top)) >= max(1, min(2, len(words(top)) // 2))


def numbers(text):
    return set(re.findall(r"(?<![A-Za-z0-9.-])\d+(?:\.\d+)?(?![A-Za-z0-9])", text))


SORT_SYS = ("You triage app-store reviews for a product team. For each numbered review decide: SPECIFIC if it names something a team "
            "could act on (a named feature, screen, setting, behaviour, device, design system such as Liquid Glass, language, price "
            "point, or a bug with circumstances); NOISE if it only gives a general feeling with nothing to act on (for example 'bad UI', "
            "'hate the new update', 'needs improvement', 'worse than before'). Group the SPECIFIC reviews into concrete requests: merge "
            "reviews asking for the same thing; write each request as a short imperative phrase of at most 9 words, concrete and "
            "neutral (for example 'Adopt Apple's Liquid Glass design', 'Stop the app taking over phone audio'). Use only what the "
            "reviews say. Reply with JSON only: {\"requests\": [{\"request\": \"...\", \"ids\": [numbers]}], \"noise_ids\": [numbers]}.")
DIR_SYS = ("You are a calm, practical product lead. From the requests below (with how many reviews ask for each), write: "
           "direction = one or two sentences saying exactly what the team should do first and why, naming the specific request(s); "
           "outcome = one sentence on what should change in reviews if it works; check = one sentence on how to tell, using the "
           "complaint's share of reviews release by release. The direction must move toward what the reviewers ask for, never the "
           "opposite. Do not invent quantities or items that are not listed. Use only numbers given here (or none). No hype, no blame, "
           "no promises about dates. Reply with JSON only: {\"direction\": \"...\", \"outcome\": \"...\", \"check\": \"...\"}.")


def main(slug):
    path = DATA / f"{slug}.analysis.json"
    a = json.loads(path.read_text())
    if a.get("sample_only") or not (DATA / f"{slug}.reviews.json").exists():
        return
    reviews = {r["id"]: r for r in json.loads((DATA / f"{slug}.reviews.json").read_text())}
    label = a["window"].get("recent_label", "90 days")
    for t in [t for t in a["themes"] if t.get("brief")]:
        rows = [reviews[i] for i in t.get("ids_recent", []) if i in reviews and (reviews[i]["body"] or reviews[i].get("title", "")).strip()]
        if len(rows) < 2:
            continue
        listing = "\n".join(f"#{j} [{r['rating']}*] {(r.get('title') or '') + ': ' if r.get('title') else ''}{r['body'][:500]}" for j, r in enumerate(rows))
        try:
            out = ask(SORT_SYS, f"App: {a['name']}\nProblem: {t['label']}\n\nReviews:\n{listing}")
        except Exception as e:  # noqa: BLE001
            print(f"  ! {slug} {t['label']}: {e}", file=sys.stderr)
            continue
        valid = lambda ids: sorted({int(i) for i in ids if str(i).lstrip("-").isdigit() and 0 <= int(i) < len(rows)})
        seen, reqs = set(), []
        for q in out.get("requests", []):
            ids = [i for i in valid(q.get("ids", [])) if i not in seen]
            name = str(q.get("request", "")).strip().rstrip(".")[:80]
            if not ids or not name:
                continue
            seen.update(ids)
            quote = best_quote(name, [rows[i] for i in ids])
            reqs.append({"request": name, "count": len(ids), "ids": [rows[i]["id"] for i in ids],
                         "quote": snippet(quote["body"], words(name)) if quote else "", "stars": quote["rating"] if quote else None})
        reqs.sort(key=lambda r: -r["count"])
        specific = len(seen)
        noise = len(rows) - specific
        act = {"n": len(rows), "specific": specific, "noise": noise, "requests": reqs[:4]}
        if reqs and reqs[0]["count"] == 1:   # no two reviews ask for the same thing: not a pattern yet
            act.update({"single": True,
                        "direction": "Each review asks for something different, so there is no single change to make first. Treat them as individual reports: reproduce any bug, and reply to feature requests asking what they need it for.",
                        "outcome": "Each reporter gets an answer, and any bug that reproduces is fixed before it spreads.",
                        "check": "If two or more reviews start asking for the same thing, it becomes a direction here on the next run."})
        elif reqs:
            allowed = {str(x) for x in [len(rows), specific, noise] + [r["count"] for r in reqs]}
            prompt = (f"App: {a['name']}. Problem: {t['label']} ({len(rows)} reviews in the last {label}; {specific} specific, {noise} too vague to act on).\n"
                      + "\n".join(f"- {r['request']}: {r['count']} review{'s' if r['count'] != 1 else ''}" for r in reqs[:4]))
            for attempt in range(3):
                try:
                    d = ask(DIR_SYS, prompt, 500)
                except Exception:  # noqa: BLE001
                    d = {}
                text = " ".join(str(d.get(k, "")) for k in ("direction", "outcome", "check"))
                tops = [r["request"] for r in reqs if r["count"] == reqs[0]["count"]]
                if d and not (numbers(text) - allowed) and any(names_top(str(d.get("direction", "")), q) for q in tops):
                    act.update({k: str(d.get(k, "")).strip() for k in ("direction", "outcome", "check")})
                    break
            if "direction" not in act:   # fall back to plain, computed text
                top = reqs[0]
                act.update({"direction": f"Start with the most-asked change: {top['request'].lower()} ({top['count']} of {len(rows)} reviews).",
                            "outcome": "Fewer reviews raising this problem after the release that ships it.",
                            "check": "Watch this complaint's share of reviews in the next release on the \"Did the fix work?\" chart."})
        t["actions"] = act
        print(f"  {slug} · {t['label']}: {specific} specific / {noise} noise; " + "; ".join(f"{r['request']} ({r['count']})" for r in reqs[:3]))
    path.write_text(json.dumps(a, ensure_ascii=False, indent=1))


def requote(slug):
    path = DATA / f"{slug}.analysis.json"
    a = json.loads(path.read_text())
    reviews = {r["id"]: r for r in json.loads((DATA / f"{slug}.reviews.json").read_text())}
    for t in a["themes"]:
        for q in (t.get("actions") or {}).get("requests", []):
            best = best_quote(q["request"], [reviews[i] for i in q.get("ids", []) if i in reviews])
            q["quote"], q["stars"] = (snippet(best["body"], words(q["request"])), best["rating"]) if best else ("", None)
    path.write_text(json.dumps(a, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if sys.argv[1:2] == ["--quotes"]:
        for s in sys.argv[2:] or list(APPS):
            if (DATA / f"{s}.reviews.json").exists() and (DATA / f"{s}.analysis.json").exists():
                requote(s)
        sys.exit()
    for s in sys.argv[1:] or list(APPS):
        if (DATA / f"{s}.analysis.json").exists():
            main(s)
