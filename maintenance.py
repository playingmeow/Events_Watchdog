"""Small due-task reminder engine, with daily nags and per-day vitamin tracking."""
import json
import os
from datetime import date, timedelta
from urllib.parse import quote
from watchdog import ROOT, SGT, datetime, send_ntfy

def monthly_cycle_start(task, today):
    day = task["day_of_month"]
    if not 1 <= day <= 28:
        raise ValueError("Monthly day must be between 1 and 28")
    start = date.fromisoformat(task["initial_due"])
    candidate = date(today.year, today.month, day)
    if candidate > today:
        year, month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
        candidate = date(year, month, day)
    return candidate if candidate >= start else None

def monthly_cycle_done(task, today):
    cycle = monthly_cycle_start(task, today)
    return cycle is not None and cycle.isoformat() in task.get("completed_cycles", [])

def due_date(task):
    if task.get("kind") == "monthly_day":
        return date.fromisoformat(task["initial_due"])
    if task.get("kind") == "daily":
        return date.fromisoformat(task["initial_due"])
    if task.get("kind") == "one_off":
        return date.fromisoformat(task["initial_due"])
    anchor = task.get("last_done")
    return (date.fromisoformat(anchor) + timedelta(days=task["interval_days"])
            if anchor else date.fromisoformat(task["initial_due"]))

def due_tasks(data, notified, today):
    result = []
    for task in data["tasks"]:
        expires_after = task.get("expires_after")
        if expires_after and today > date.fromisoformat(expires_after):
            continue
        if not task.get("enabled", True) or due_date(task) > today:
            continue
        if task.get("kind") == "monthly_day":
            if monthly_cycle_start(task, today) is None or monthly_cycle_done(task, today):
                continue
            result.append(task)
            continue
        if task.get("kind") == "one_off":
            # One-off alerts are valid only on the specified day and never nag later.
            if due_date(task) != today or notified.get(task["id"]) == "sent":
                continue
            result.append(task)
            continue
        if task.get("kind") == "daily":
            # Each day has its own Done record. No retroactive assumptions.
            if today.isoformat() in task.get("completed_dates", []):
                continue
        elif task.get("last_done") and date.fromisoformat(task["last_done"]) >= today:
            continue
        if task.get("nag_daily", False) or notified.get(task["id"]) != (task.get("last_done") or "initial"):
            result.append(task)
    return result

def send_dashboard_notice(title, message, dashboard_url):
    from urllib.request import Request, urlopen
    from urllib.parse import quote as urlquote
    server = (os.getenv("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
    headers = {"Title": title.replace("—", "-").replace("–", "-"), "Tags": "calendar", "Content-Type": "text/plain; charset=utf-8", "Click": dashboard_url}
    if os.getenv("NTFY_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["NTFY_TOKEN"]
    req = Request(server + "/" + urlquote(os.environ["NTFY_TOPIC"], safe=""), data=message.encode("utf-8"), headers=headers, method="POST")
    with urlopen(req, timeout=12) as resp:
        resp.read()

def send_weekly_dashboard(today, notified, dry_run):
    key = "weekly-dashboard-review"
    test_run = today == date(2026, 11, 12)
    if (today.weekday() != 6 and not test_run) or notified.get(key) == today.isoformat():
        return
    if dry_run:
        print("[DRY RUN] Weekly dashboard review link")
        return
    base = os.getenv("FEEDBACK_BASE_URL", "").rstrip("/")
    if not base.startswith("https://"):
        raise ValueError("FEEDBACK_BASE_URL required for weekly dashboard link")
    dashboard_url = base + "/dashboard"
    send_dashboard_notice(
        "Dashboard review test" if test_run else "Sunday dashboard review",
        "Review your reminders and overdue items. Add anything you want to track for the week ahead.\n\n" + dashboard_url,
        dashboard_url,
    )
    notified[key] = today.isoformat()

def run_maintenance(dry_run=False):
    data = json.loads((ROOT / "maintenance.json").read_text())
    state_path = ROOT / "state.json"
    state = json.loads(state_path.read_text())
    notified = state.setdefault("maintenance_notified", {})
    today = datetime.now(SGT).date()
    tasks = due_tasks(data, notified, today)
    print(f"[TASKS] due={len(tasks)}")
    for task in tasks:
        if dry_run:
            print("[DRY RUN TASK]", task["name"])
            continue
        base = os.getenv("FEEDBACK_BASE_URL", "").rstrip("/")
        if not base.startswith("https://"):
            raise ValueError("FEEDBACK_BASE_URL required for Done buttons")
        link = base + "/maintenance/done?task=" + quote(task["id"], safe="")
        if task.get("kind") == "monthly_day":
            link += "&cycle=" + monthly_cycle_start(task, today).isoformat()
        if task.get("kind") == "one_off":
            send_dashboard_notice(task["name"], task["message"], base + "/dashboard")
            notified[task["id"]] = "sent"
            continue
        watch = {"name": "Meow reminders"}
        item = {"title": task["name"] + " — due" + (" (overdue)" if task.get("kind") != "monthly_day" and due_date(task) < today else ""), "link": link}
        send_ntfy(os.environ["NTFY_TOPIC"], watch, item, link, action_label="Done")
        notified[task["id"]] = task.get("last_done") or "initial"
    send_weekly_dashboard(today, notified, dry_run)
    if not dry_run:
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not os.getenv("NTFY_TOPIC"):
        raise SystemExit("NTFY_TOPIC required")
    run_maintenance(args.dry_run)
