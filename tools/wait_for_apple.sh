#!/bin/sh
# Waits for Apple's customer-review feed to come back (it returned empty lists for every app from the afternoon of
# 27 Nov 2026), then runs the local pipeline for the apps given (default: BeFunky and Visionn) and exits so the
# session can review the cards before anything is published. Nothing here pushes or deploys.
# Usage: tools/wait_for_apple.sh [slug ...]   Log: data/wait-apple.log
cd "$(dirname "$0")/.." || exit 1
PY=/opt/homebrew/bin/python3
SLUGS="${*:-befunky visionn}"
LOG=data/wait-apple.log
probe() {  # Letterboxd's US feed: a well-reviewed app, so zero entries means the feed itself is empty
  curl -s -m 20 -A "Mozilla/5.0 (Macintosh) review-radar/0.2" \
    "https://itunes.apple.com/us/rss/customerreviews/page=1/id=1054271011/sortBy=mostRecent/json" | grep -o '"im:rating"' | wc -l | tr -d ' '
}
i=0
while [ $i -lt 48 ]; do  # every 15 minutes for up to 12 hours
  n=$(probe)
  echo "$(date '+%Y-%m-%d %H:%M') probe: ${n:-0} reviews" >> "$LOG"
  if [ "${n:-0}" -gt 0 ]; then
    echo "$(date '+%H:%M') feed is back; running the pipeline for: $SLUGS" >> "$LOG"
    $PY -I tools/fetch.py $SLUGS >> "$LOG" 2>&1
    for s in $SLUGS; do
      c=$($PY -I -c "import json;print(len(json.load(open('data/$s.reviews.json'))))" 2>/dev/null)
      echo "$(date '+%H:%M') $s: ${c:-0} reviews fetched" >> "$LOG"
    done
    $PY -I tools/tag.py $SLUGS >> "$LOG" 2>&1 && \
    $PY -I tools/analyse.py $SLUGS >> "$LOG" 2>&1 && \
    $PY -I tools/brief.py $SLUGS >> "$LOG" 2>&1 && \
    $PY -I tools/fixes.py $SLUGS >> "$LOG" 2>&1 && \
    $PY -I tools/stats.py $SLUGS >> "$LOG" 2>&1 && \
    $PY -I tools/translate.py $SLUGS >> "$LOG" 2>&1 && \
    $PY -I tools/build.py >> "$LOG" 2>&1
    echo "$(date '+%H:%M') DONE (local only; review before publishing)" >> "$LOG"
    exit 0
  fi
  i=$((i + 1))
  sleep 900
done
echo "$(date '+%H:%M') GAVE UP after 12 hours: Apple's feed still empty" >> "$LOG"
exit 2
