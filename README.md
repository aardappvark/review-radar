# Review Radar

Every recent written App Store review of an app, read by a local model and turned into the handful of problems worth a look this week: the evidence, the version it started in, incident spikes, and a reply ready to post.

Live: https://aardappvark.github.io/review-radar/

Built in one sitting (27 Nov 2026, 1:53–2:28 pm Melbourne) as a demo on two Tiny companies' apps, Letterboxd and Serato DJ. Independent; not affiliated with either.

## Run it

```bash
python3 tools/fetch.py      # Apple's public review feed: 500 most recent per storefront, 6 storefronts
python3 tools/tag.py        # local gemma4 (Ollama): theme list, then 0-2 themes + bug flag + gist per review
python3 tools/analyse.py    # themes and trend, version regressions, bursts, copy-paste text
python3 tools/brief.py      # local gemma4 26B drafts the top-5 cards; numbers checked against the data
python3 tools/build.py      # one self-contained docs/index.html (served by GitHub Pages)
```

Needs Python 3.10+ and [Ollama](https://ollama.com) with `gemma4` and `gemma4:26b`. No API keys, no spend.

## What it does

| Step | How |
| --- | --- |
| Themes | The model reads a sample of low-star reviews and proposes the theme list itself, then tags every review. Hand check: 28 of 30 matched. |
| Ranking | Reviews in the last 90 days, 1–2★ counted double; trend against the 90 days before. |
| Incidents | A day with at least five times the normal count (and at least six reviews) is flagged; launch week is skipped. The alert time is when the third matching low-star review landed. |
| Versions | Written-review average per release, flagged when it drops half a star or more. |
| Copy-paste | Near-identical text across different reviews (3-word shingles, Jaccard ≥ 0.6). |
| Briefs | Drafted by the local model. Any number it writes that isn't in the data sends the card back, then falls back to a plain sentence. |

## Limits

Written reviews are a loud minority (star-only ratings aren't in the feed), so they show where to look, not how many people are affected. Apple's feed stops at 500 reviews per storefront. Reviewer names are never stored.
