#!/usr/bin/env python3
"""Write the top-problem cards with the local model, then check every number it wrote.

For the top 5 complaint themes: headline, what is happening, where to look, suggested action,
and a drafted developer reply to one real review. Any number in the model's text that is not
in the stats we gave it gets the card regenerated (then dropped to a plain template).
"""
import json, re, sys, pathlib, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent / "data"
MODEL = "gemma4:26b"


def ask(prompt):
    body = json.dumps({"model": MODEL, "prompt": prompt, "stream": False, "think": False, "format": "json",
                       "options": {"temperature": 0.2, "num_predict": 900}}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(json.load(r)["response"])


VERSION = re.compile(r"\bv?(\d+\.\d+\.\d+(?:\.\d+)?)\b")
PROMISE = re.compile(r"\b(we are|we're|our team is|team is)\s+(\w+\s+)?(looking into|working|investigating|fixing|adding|planning)|\bwe will\b|\bwe'll\b|\bcoming soon\b|\bin the next (update|release)\b", re.I)
FIELDS = ("headline", "happening", "where_to_look", "action", "reply")


def numbers(text):
    """Standalone numbers. Version strings are checked on their own; digits inside names (FLX10, MK2) are names."""
    text = VERSION.sub(" ", text)
    return set(re.findall(r"(?<![A-Za-z0-9.-])\d+(?:\.\d+)?(?![A-Za-z0-9])", text))


def problems(field, text, allowed, versions):
    bad = sorted(numbers(text) - allowed) + [v for v in VERSION.findall(text) if v not in versions]
    if field == "reply" and PROMISE.search(text):
        bad.append("promise: " + PROMISE.search(text).group(0))
    return bad


def trend(t):
    if not t["n_prior"]:
        return "new: no reviews raised it in the previous period (do not call it rising or increasing)"
    r = (t["n_recent"] - t["n_prior"]) / t["n_prior"]
    if abs(r) < 0.15:
        return "steady compared with the previous period"
    return "rising compared with the previous period" if r > 0 else "falling compared with the previous period"


def card(app, t, versions, label="90 days"):
    allowed = {str(x) for x in [t["n_recent"], t["n_prior"], t["low_recent"], t["n"], t["avg_recent"], t["avg"],
                                 round(t["bug_share"] * 100), round(t["share_recent"] * 100), 90, 12, t.get("pos_recent", 0)]}
    for q in t["quotes"]:
        allowed |= numbers(q["version"]) | numbers(q["text"]) | numbers(q["title"])
    for g in t["gists"]:
        allowed |= numbers(g)
    for v in versions:
        allowed |= numbers(v["version"])
    gist = "\n".join(f"- {g}" for g in t["gists"])
    qs = "\n".join(f"[{i}] {q['stars']}* v{q['version']} {q['date']}: {q['title']} — {q['text']}" for i, q in enumerate(t["quotes"]))
    vers = ", ".join(f"v{v['version']} ({v['n']} reviews, avg {v['avg']})" for v in versions[-6:])
    prompt = f"""You are a senior product manager at {app}. Write a short, specific brief about one complaint theme
from its public app-store reviews. Be concrete and calm; no hype, no blame.

Theme: {t['label']} — {t['describe']}
Trend: {trend(t)}
Stats (last {label}): {t['n_recent']} reviews mention it (previous {label}: {t['n_prior']}); {t.get('pos_recent', 0)} of them are 4-5 stars and {t['low_recent']} are 1-2 stars.
If most mentions are positive, say so first and describe the complaints as a minority; never present praise as a complaint;
average rating {t['avg_recent']}; {round(t['share_recent'] * 100)}% of all recent reviews; {round(t['bug_share'] * 100)}% report something broken.
Recent versions: {vers}

One-line gists of recent low-star reviews:
{gist}

Example reviews:
{qs}

Rules: use ONLY numbers that appear above (or none). Do not invent features, dates, causes, trends or quotes.
"where_to_look" names a product area or user flow (e.g. "the sign-in flow after an update"), never a guess about code.
The reply must not promise work or claim the team is already doing something; it can thank, acknowledge the specific
problem, and invite them to contact support. Never name a menu path, email address or URL.
Return JSON:
{{"headline": "max 9 words, plain", "happening": "2 sentences on what users report", "where_to_look": "1 sentence: the product area or flow an engineer should check first",
 "action": "1 sentence: the smallest next step for the team this week", "reply_to": 0, "reply": "a public App Store developer reply to that example review, max 55 words, warm, specific, no promises of dates, no discounts"}}"""
    known = {v["version"] for v in versions} | {q["version"] for q in t["quotes"]}
    safe = {
        "headline": t["label"],
        "happening": f"{t['n_recent']} reviews in the last {label} raise this ({t['low_recent']} at 1–2 stars).",
        "where_to_look": "The flows named in the evidence below.",
        "action": "Read the evidence below and reproduce the most common report on the current version.",
        "reply": "Thank you for taking the time to write this. We're sorry about the trouble, and we'd like to hear more: please contact our support team with the details.",
    }
    out, issues = {}, {}
    for attempt in range(2):
        out = ask(prompt)
        issues = {f: problems(f, str(out.get(f, "")), allowed, known) for f in FIELDS}
        issues = {f: v for f, v in issues.items() if v or not str(out.get(f, "")).strip()}
        if not issues:
            out["checked"] = True
            return out
        print(f"    retry {t['label']}: {issues}")
    for f in issues:  # only the fields that failed fall back to plain, safe text
        out[f] = safe[f]
    out["checked"] = "partial: " + ", ".join(sorted(issues))
    return out


def mostly_positive(t, out, label):
    """When praise outnumbers complaints at least two to one, the card must say so: facts from the counts, not the model."""
    pos, low, n = t.get("pos_recent", 0), t["low_recent"], t["n_recent"]
    if pos >= 2 * max(low, 1):
        out["headline"] = f"{t['label']}: raised mostly in happy reviews"
        out["happening"] = (f"Of the {n} reviews in the last {label} that raise this, {pos} are 4–5 stars and {low} {'is' if low == 1 else 'are'} 1–2 stars: "
                            f"it comes up mostly as a request or a side note from people who like the app. The evidence below shows the unhappy "
                            f"{'one' if low == 1 else 'ones'}.")
        out["checked"] = "counts"
    return out


def main(slug):
    p = ROOT / f"{slug}.analysis.json"
    a = json.loads(p.read_text())
    # A "problem" needs at least one angry review behind it; a theme people mostly praise is not a problem card.
    top = [t for t in a["themes"] if t["key"] != "praise" and t["n_recent"] >= 2 and t["low_recent"] >= 1][:5]
    for t in top:
        print(f"  {a['name']}: {t['label']}")
        L = a["window"].get("recent_label", "90 days")
        t["brief"] = mostly_positive(t, card(a["name"], t, a["versions"], L), L)
    p.write_text(json.dumps(a, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    for s in sys.argv[1:] or [a["slug"] for a in json.loads((ROOT.parent / "apps.json").read_text())]:
        main(s)
