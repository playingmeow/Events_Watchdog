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

## MakeIT booking snapshot writer

`makeit-sync.yml` runs at **08:15 Singapore time** each day. It reads SimplyBook messages using Gmail search `in:anywhere -in:spam` (so Trash is included), reconciles future bookings against the primary Google Calendar, and commits only the minimal public booking snapshot. If Gmail and Calendar disagree, it fails without replacing the snapshot. The morning reminder skips the MakeIT section when the last successful snapshot is over 20 hours old; other maintenance reminders continue normally.

### Google credentials

The scheduled writer needs these repository Actions secrets:

- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REFRESH_TOKEN`

Create a Google Cloud project, enable Gmail API and Google Calendar API, then configure an OAuth consent screen and OAuth client. Generate an offline refresh token for these read-only scopes:

- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/calendar.events.readonly`

You can generate it in Google's OAuth 2.0 Playground by selecting **Use your own OAuth credentials**, setting the Playground URL as the OAuth client's redirect URI, enabling offline access and consent, then authorizing those scopes. Add the three values directly in **GitHub → Settings → Secrets and variables → Actions**. Never commit or paste the refresh token into an issue, PR, or chat.

**Google OAuth caveat:** Gmail's `gmail.readonly` scope is classified as restricted. For a one-person personal-use app, Google's verification guidance describes a personal-use exception, but consent may show an unverified-app warning. An external OAuth app left in **Testing** issues refresh tokens that expire after 7 days, so that mode is suitable only for a short trial. Confirm Google's current verification and data-handling requirements before publishing the app for ongoing use.

After merging and adding the credentials, use **Actions → MakeIT booking sync → Run workflow** with `dry_run=true` to check the reconciliation before the first write. If the output matches, dispatch again with `dry_run=false`; the daily schedule then runs at its next 08:15 Singapore occurrence.
\n