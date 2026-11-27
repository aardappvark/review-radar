# Build log, 27 Nov 2026 (Melbourne time, AEDT)

| Time | Step |
| --- | --- |
| 13:53 | Start. Picked the apps: Letterboxd (88,436 ratings, 4.82★) and Serato DJ (launched 18 Oct, 3.85★). Dribbble and AeroPress have no official iOS app. |
| 13:54 | Fetched 1,429 written reviews from Apple's public feed (6 storefronts). |
| 13:55 | Local model proposed the Serato theme list and tagged all 59 reviews in 78 seconds. Spot check: 10 of 10 sensible. |
| 13:56 | Letterboxd theme list proposed; tagging 1,370 reviews in the background (~25 min on gemma4). |
| 13:57 | Found the 9 Aug Letterboxd incident: 27 reviews in three days on v4.12.3, almost all sign-out / can't sign back in. |
| 13:58 | Analysis step: themes and trend, versions, bursts (launch week excluded after Serato's launch days showed up as false bursts), copy-paste detection. |
| 14:00 | Page template and the brief step (numbers checked against the data). |
| 14:08 | Hand check of 30 random Letterboxd tags: 28 agree. |
| 14:12 | Serato briefs: the checker caught invented trends ("rising" for a brand-new app) and code-level guesses; prompt tightened. |
| 14:23 | Letterboxd tagging done (1,370/1,370 after one retry pass). |
| 14:24 | Burst times moved to Pacific (the feed's own clock); a UTC display had put one alert before its first review. |
| 14:25 | Checker made per-field: unknown numbers or versions, or a reply that promises work, send the card back. Caught a "we are looking into" reply. |
| 14:26 | Ranking changed to 1–2★ count first: a 4.15★ feature-request theme had ranked above crash reports. |
| 14:28 | Page built and checked: desktop, phone width (no sideways scroll), dark mode, tab switching, 0 JS errors. Finished. |
| 17:18 | Extended to every Tiny company with public app reviews: tiny.com lists 21 companies; App Store sellers checked by name (only Letterboxd, Serato, BeFunky publish iOS apps); Shopify developer pages confirmed Stamped, KNO, Foursixty, Out of the Sandbox. |
| 17:21 | Shopify reader done: 939 reviews; store names never stored (a review whose layout isn't recognised keeps its stars only). Apple's feed returned nothing from two networks, so BeFunky and Visionn wait. |
| 17:25 | MCP server written and deployed on Cloudflare Workers, reading the published data; six tools. |
| 17:37 | Shopify tagging done. Quiet apps get a 12-month window; praise buckets normalised; an accusatory theme label ("Bait-and-Switch") neutralised. |
| 17:43 | Caught cards presenting mostly-praise themes as problems (Stamped support: 15 of 21 are 4–5★). Rule: a problem needs a 1–2★ review, and a theme raised mostly in happy reviews says so, from the counts. Cards redrafted. |
| 17:44 | Published. (Times in this table come from file timestamps.) |
