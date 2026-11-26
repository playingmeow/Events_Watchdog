#!/usr/bin/env python3
"""Rebuild the MakeIT booking snapshot from Gmail (including Trash) and Calendar."""
import argparse
import base64
import html
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

SGT = ZoneInfo("Asia/Singapore")
TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"
SENDER = "no-reply-makeitsg.asia@simplybook.me"
SNAPSHOT = "makeit_bookings.json"


def api_json(url, headers=None, data=None):
    req = Request(url, headers=headers or {}, data=data)
    try:
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Google API request failed for {url.split('?')[0]}: {exc}") from exc


def access_token():
    required = ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REFRESH_TOKEN")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError("Missing GitHub Actions secrets: " + ", ".join(missing))
    body = urlencode({
        "client_id": os.environ["GOOGLE_OAUTH_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    token = api_json(TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"}, body)
    if not token.get("access_token"):
        raise RuntimeError("Google did not return an access token")
    return token["access_token"]


def google_headers(token):
    return {"Authorization": "Bearer " + token, "Accept": "application/json"}


def gmail_messages(headers):
    query = urlencode({"q": f"in:anywhere -in:spam from:{SENDER} newer_than:400d", "maxResults": 100})
    url = f"{GMAIL_API}/messages?{query}"
    while url:
        page = api_json(url, headers)
        for item in page.get("messages", []):
            yield api_json(f"{GMAIL_API}/messages/{item['id']}?format=full", headers)
        next_token = page.get("nextPageToken")
        url = f"{GMAIL_API}/messages?{urlencode({'q': f'in:anywhere -in:spam from:{SENDER} newer_than:400d', 'maxResults': 100, 'pageToken': next_token})}" if next_token else None


def decode_part(part):
    value = part.get("body", {}).get("data")
    if not value:
        return ""
    raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    charset = "utf-8"
    for header in part.get("headers", []):
        if header.get("name", "").lower() == "content-type":
            match = re.search(r"charset=[\"']?([^;\"']+)", header.get("value", ""), re.I)
            if match:
                charset = match.group(1)
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def message_bodies(payload):
    if payload.get("mimeType", "").startswith("text/"):
        yield payload.get("mimeType"), decode_part(payload)
    for part in payload.get("parts", []):
        yield from message_bodies(part)


def header_value(message, name):
    return next((h.get("value", "") for h in message.get("payload", {}).get("headers", [])
                 if h.get("name", "").lower() == name.lower()), "")


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def reservations_from(value):
    found = []
    if isinstance(value, dict):
        typ = value.get("@type", "")
        if typ == "EventReservation" or (isinstance(typ, list) and "EventReservation" in typ):
            found.append(value)
        for child in value.values():
            found.extend(reservations_from(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(reservations_from(child))
    return found


def jsonld_objects(source):
    objects = []
    for match in re.finditer(r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", source, re.I | re.S):
        raw = html.unescape(match.group(1)).strip()
        try:
            objects.extend(reservations_from(json.loads(raw)))
        except json.JSONDecodeError:
            pass
    if not objects:
        # Some email clients wrap or truncate script tags; scan for valid JSON objects.
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", source):
            try:
                parsed, _ = decoder.raw_decode(source[match.start():])
            except json.JSONDecodeError:
                continue
            objects.extend(reservations_from(parsed))
            if objects:
                break
    return objects


def nested_name(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("name", "streetAddress", "addressLocality"):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key].strip()
        address = value.get("address")
        if address:
            return nested_name(address)
    return ""


def parse_email(message):
    headers = message.get("payload", {}).get("headers", [])
    subject = header_value(message, "Subject")
    plain, markup = [], []
    for mime, body in message_bodies(message.get("payload", {})):
        (markup if mime == "text/html" else plain).append(body)
    source = "\n".join(markup)
    text = "\n".join(plain)
    if source:
        parser = TextExtractor()
        parser.feed(source)
        text += "\n" + " ".join(parser.parts)
    text = html.unescape(text)
    canceled = bool(re.search(r"\b(cancel(?:led|ed|lation)?|cancellation confirmed)\b", subject + "\n" + text, re.I))
    objects = []
    for body in markup:
        objects.extend(jsonld_objects(body))
    if not objects:
        for body in plain:
            objects.extend(jsonld_objects(body))
    if not objects:
        if canceled:
            raise RuntimeError(f"Cancellation email {message.get('id')} has no readable reservation data")
        return None

    reservation = objects[0]
    event = reservation.get("reservationFor") or {}
    reservation_id = str(reservation.get("reservationId") or "").strip()
    urls = re.findall(r"(?:booking|reservation)(?:/|=|%3D)(\d{4,})", source + "\n" + text, re.I)
    booking_number = re.search(r"\bbooking\s*(?:id|number|#)?\s*[:#]?\s*(\d{4,})\b", text, re.I)
    numeric_id = booking_number.group(1) if booking_number else (urls[0] if urls else "")
    if not numeric_id:
        # SimplyBook's confirmation links commonly place the number in a query parameter.
        match = re.search(r"[?&](?:booking_?id|id)=(\d{4,})", source, re.I)
        numeric_id = match.group(1) if match else ""
    if not numeric_id:
        raise RuntimeError(f"Could not identify numeric booking ID in Gmail message {message.get('id')}")

    start = event.get("startDate")
    if not start:
        raise RuntimeError(f"Reservation {numeric_id} has no event start date")
    try:
        when = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        if when.tzinfo is None:
            raise ValueError("missing timezone")
        when = when.astimezone(SGT)
    except ValueError as exc:
        raise RuntimeError(f"Reservation {numeric_id} has invalid start date: {start}") from exc

    location = nested_name(event.get("location")) or nested_name(event.get("locationCreated"))
    service = nested_name(event.get("name")) or subject
    internal_date = int(message.get("internalDate", "0"))
    if internal_date:
        received = datetime.fromtimestamp(internal_date / 1000, timezone.utc)
    else:
        received = parsedate_to_datetime(header_value(message, "Date")).astimezone(timezone.utc)
    return {
        "booking_id": numeric_id,
        "reservation_id": reservation_id,
        "service": service,
        "date": when.date().isoformat(),
        "time": when.strftime("%H:%M"),
        "location": location,
        "cancelled": canceled,
        "received": received,
        "message_id": message.get("id", ""),
    }


def latest_email_state(headers):
    latest = {}
    for message in gmail_messages(headers):
        record = parse_email(message)
        if not record:
            continue
        previous = latest.get(record["booking_id"])
        if previous is None or record["received"] > previous["received"]:
            latest[record["booking_id"]] = record
    if not latest:
        raise RuntimeError("Gmail search returned no parseable SimplyBook booking messages")
    return latest


def calendar_events(headers, today):
    start = datetime.combine(today - timedelta(days=400), datetime.min.time(), SGT).isoformat()
    end = datetime.combine(today + timedelta(days=400), datetime.max.time(), SGT).isoformat()
    params = {
        "timeMin": start, "timeMax": end, "q": "SimplyBook",
        "showDeleted": "true", "singleEvents": "true", "maxResults": 2500,
    }
    url = f"{CALENDAR_API}/calendars/primary/events?{urlencode(params)}"
    while url:
        page = api_json(url, headers)
        for item in page.get("items", []):
            yield item
        token = page.get("nextPageToken")
        url = f"{CALENDAR_API}/calendars/primary/events?{urlencode({**params, 'pageToken': token})}" if token else None


def calendar_index(headers, today):
    result = {}
    for event in calendar_events(headers, today):
        description = event.get("description", "")
        summary = event.get("summary", "")
        match = re.search(r"\bSimplyBook\s+booking\s+#?(\d{4,})\b", summary + "\n" + description, re.I)
        if match:
            result[match.group(1)] = event
    return result


def build_snapshot(headers, today):
    emails = latest_email_state(headers)
    events = calendar_index(headers, today)
    rows = []
    mismatches = []
    for booking_id, record in emails.items():
        if record["cancelled"]:
            continue
        if date.fromisoformat(record["date"]) < today:
            continue
        event = events.get(booking_id)
        if not event:
            mismatches.append(f"Gmail confirms future booking {booking_id}, but no matching Calendar event was found")
            continue
        if event.get("status") == "cancelled":
            mismatches.append(f"Gmail confirms booking {booking_id}, but its Calendar event is cancelled")
            continue
        start = event.get("start", {}).get("dateTime")
        if not start:
            mismatches.append(f"Calendar event for booking {booking_id} has no timed start")
            continue
        calendar_start = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(SGT)
        if calendar_start.date().isoformat() != record["date"] or calendar_start.strftime("%H:%M") != record["time"]:
            mismatches.append(f"Gmail and Calendar disagree on date/time for booking {booking_id}")
            continue
        if not record["location"]:
            mismatches.append(f"Gmail reservation {booking_id} has no location")
            continue
        rows.append({
            "source": "SimplyBook",
            "service": record["service"],
            "date": record["date"],
            "time": record["time"],
            "location": record["location"],
        })

    for booking_id, event in events.items():
        start = event.get("start", {}).get("dateTime")
        if event.get("status") == "cancelled" or not start:
            continue
        if datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(SGT).date() < today:
            continue
        record = emails.get(booking_id)
        if record is None:
            mismatches.append(f"Future Calendar booking {booking_id} has no matching Gmail record")
        elif record["cancelled"]:
            # The cancellation email is authoritative when an old Calendar item lingers.
            continue
    if mismatches:
        raise RuntimeError("Gmail/Calendar reconciliation failed; snapshot left untouched:\n- " + "\n- ".join(mismatches))
    rows.sort(key=lambda b: (b["date"], b["time"], b["source"], b["service"]))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bookings": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    token = access_token()
    today = datetime.now(SGT).date()
    snapshot = build_snapshot(google_headers(token), today)
    rendered = json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"
    if args.dry_run:
        print(rendered, end="")
        print("[DRY RUN] Snapshot not written.")
        return
    with open(SNAPSHOT, "w", encoding="utf-8") as output:
        output.write(rendered)
    print(f"Wrote {len(snapshot['bookings'])} active booking(s) to {SNAPSHOT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
