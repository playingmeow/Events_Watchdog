"""Public MakeIT booking snapshot used by the existing morning Watchdog."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PATH = Path(__file__).with_name("makeit_bookings.json")
MAX_SNAPSHOT_AGE = timedelta(hours=20)


class StaleSnapshotError(ValueError):
    """Raised when the booking writer has not produced a recent reconciled snapshot."""


def snapshot_is_fresh(path=PATH, now=None):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        generated = datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))
        if generated.tzinfo is None:
            return False
        age = (now or datetime.now(timezone.utc)) - generated.astimezone(timezone.utc)
        return timedelta(0) <= age <= MAX_SNAPSHOT_AGE
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def upcoming_bookings(today, days=7, path=PATH):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StaleSnapshotError("snapshot is missing or invalid") from exc
    if not snapshot_is_fresh(path):
        raise StaleSnapshotError("snapshot missing a recent successful Gmail/Calendar sync")
    end = today + timedelta(days=days - 1)
    result = []
    for item in data.get("bookings", []):
        if not all(isinstance(item.get(k), str) and item[k].strip()
                   for k in ("source", "service", "date", "time", "location")):
            continue
        try:
            when = date.fromisoformat(item["date"])
        except ValueError:
            continue
        if today <= when <= end:
            result.append(item)
    return sorted(result, key=lambda b: (b["date"], b["time"], b["source"]))


def format_bookings(bookings):
    return "Upcoming MakeIT bookings (next 7 days):\n" + "\n".join(
        f"{b['date'][8:10]}/{b['date'][5:7]} {b['time']} — {b['source']} / {b['service']} — {b['location']}"
        for b in bookings
    )
