# Review Radar

Every recent written App Store review of an app, read by a local model and turned into the handful of problems worth a look this week: the evidence, the version it started in, incident spikes, and a reply ready to post.

Live: https://aardappvark.github.io/review-radar/

First version built in one sitting (27 Nov 2026, 1:53–2:28 pm Melbourne) on Letterboxd and Serato DJ, then extended the same day to all eight of Tiny's public apps: BeFunky and Visionn (App Store) and Stamped, KNO, Foursixty and Out of the Sandbox (Shopify App Store). BeFunky and Visionn come through the iTunes store's own review endpoint, because Apple's customer-review RSS went empty for every app on 27 Nov 2026 (it carries developer replies but no app version). Letterboxd also gets **Around the world**: 12 more countries' App Stores, kept apart from its English analysis. Independent; not affiliated with Tiny or any of these companies.

**For agents:** `claude mcp add --transport http review-radar https://review-radar.aardappvark.workers.dev/mcp` (source in `mcp/`; tools: list_apps, top_problems, incidents, versions, did_the_fix_work, review_stats, themes, draft_reply).

## Run it

```bash
python3 tools/fetch.py      # apps.json: Apple's review feed (500 per storefront, 6 storefronts) and Shopify App Store review pages
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
| Did the fix work? | Each complaint's share of each release's reviews; the most recent spike is tracked, and the verdict (fell after vX, easing, still open, too early) is read from the numbers. A drop is consistent with a fix, not proof. |
| Dig into the numbers | Star mix (this period vs the last), written reviews and average stars by month, reviewer countries, three-word reviews, median length, and publisher reply rate on Shopify. |
| Translations | Quotes not in English are shown translated first (local model), with "tap for original"; an "In other languages" panel counts and samples them. |
| Copy-paste | Near-identical text across different reviews (3-word shingles, Jaccard ≥ 0.6). |
| Briefs | Drafted by the local model. Any number it writes that isn't in the data sends the card back, then falls back to a plain sentence. |

## Limits

Written reviews are a loud minority (star-only ratings aren't in the feed), so they show where to look, not how many people are affected. Apple's feed stops at 500 reviews per storefront. Reviewer names are never stored.
