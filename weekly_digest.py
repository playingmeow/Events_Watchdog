"""Sunday Meow reminder digest from the existing maintenance registry."""
import json
import os
from datetime import date, timedelta
from urllib.parse import urlencode
from maintenance import due_date
from watchdog import ROOT, SGT, datetime, send_ntfy

def build_digest(data, today):
    week_end = today + timedelta(days=6)
    overdue, this_week, later, completed = [], [], [], []
    for task in data["tasks"]:
        if task.get("enabled", True) is False:
            continue
        name = task["name"]
        if task.get("kind") == "daily":
            if today >= date.fromisoformat(task["initial_due"]):
                (completed if today.isoformat() in task.get("completed_dates", []) else this_week).append(name)
            continue
        due = due_date(task)
        if due < today:
            overdue.append(name + " (" + due.isoformat() + ")")
        elif due <= week_end:
            this_week.append(name + " (" + due.isoformat() + ")")
        else:
            later.append((due, name))
        if any(today - timedelta(days=7) <= date.fromisoformat(h["done"]) <= today for h in task.get("history", [])):
            completed.append(name)
    later.sort()
    parts = ["Meow Reminders — Sunday " + today.isoformat()]
    for heading, items in [
        ("Overdue", overdue), ("Due next 7 days", this_week),
        ("Coming up (next 5)", [n + " (" + d.isoformat() + ")" for d,n in later[:5]]),
        ("Completed in past 7 days", completed)]:
        parts.append(heading + " (" + str(len(items)) + "):")
        parts.extend("• " + item for item in items) if items else parts.append("• None")
    return "\n".join(parts)

def main():
    today = datetime.now(SGT).date()
    if today.weekday() != 6 and os.environ.get("ALLOW_NON_SUNDAY") != "true":
        print("Not Sunday in Singapore; skipping.")
        return
    data = json.loads((ROOT / "maintenance.json").read_text())
    digest = build_digest(data, today)
    dashboard = os.environ.get("FEEDBACK_BASE_URL", "").rstrip("/") + "/dashboard"
    if not dashboard.startswith("https://"):
        raise ValueError("FEEDBACK_BASE_URL must be https")
    if os.environ.get("DRY_RUN") == "true":
        print(digest + "\nDashboard: " + dashboard)
        return
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        raise ValueError("NTFY_TOPIC not configured")
    send_ntfy(topic, {"name": "Meow reminders"}, {"title": digest, "link": dashboard}, dashboard, action_label="Open dashboard")
    print("Sunday digest sent")

if __name__ == "__main__":
    main()
