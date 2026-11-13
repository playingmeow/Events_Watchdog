"""Public MakeIT booking snapshot used by the existing morning Watchdog."""
import json
from datetime import date, timedelta
from pathlib import Path

PATH = Path(__file__).with_name("makeit_bookings.json")

def upcoming_bookings(today, days=7, path=PATH):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
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
