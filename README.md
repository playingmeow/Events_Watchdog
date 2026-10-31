# Events Watchdog 🐱

Weekly public-news monitoring for promotions and local events, with ntfy notifications.

## Current watchlist
- **Yakiniku-GO:** October anniversary promotions and other deals.
- **Singapore Airlines:** Time To Fly and airfare sales.
- **Heartbeat@Bedok:** publicly indexed event announcements.

Edit `watchlist.json` to add watches and sources. Current sources are Google News RSS and Bing News RSS. **These are not official event calendars**: social-only promotions and some Heartbeat events may be missed. Event dates are not yet parsed or checked against the future.

## Setup
1. GitHub **Settings → Secrets and variables → Actions → New repository secret**: add `NTFY_TOPIC` (your private ntfy topic).
2. Optional: add `NTFY_TOKEN` secret for authenticated ntfy; set `NTFY_SERVER` repository variable if not using `https://ntfy.sh`.
3. Open **Actions → Events Watchdog → Run workflow**, leave **dry_run=true**. Inspect the output; no notification or state changes occur.
4. When satisfied, run with **dry_run=false**. This first live run records a baseline without notifying about old results. Future newly discovered matching links trigger ntfy.
5. Scheduled runs are **Saturdays 09:15 Singapore time** (01:15 UTC), subject to GitHub scheduling delays. With no `NTFY_TOPIC`, live runs safely skip.

## Safety
- 3-minute Actions timeout, weekly cadence, deduplication, first-run baseline, and manual dry-run mode.
- Never commit ntfy topics, tokens or private calendar details to this public repository.
- The public `state.json` contains hashes and dates of seen public links, not credentials.
- If all sources fail for a watch, its baseline is not marked complete.

## Scope limitations / next phase
- News RSS discovery is a pilot; official Heartbeat@Bedok listings need a dedicated source.
- Event expiry filtering and Attend / Not Interested → Calendar callbacks are **not yet implemented**.
- No automated booking.
