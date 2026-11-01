"""Small due-task reminder engine, with daily nags and per-day vitamin tracking."""
import json
import os
from datetime import date, timedelta
from urllib.parse import quote
from watchdog import ROOT, SGT, datetime, send_ntfy

def due_date(task):
    if task.get("kind") == "daily":
        return date.fromisoformat(task["initial_due"])
    anchor = task.get("last_done")
    return (date.fromisoformat(anchor) + timedelta(days=task["interval_days"])
            if anchor else date.fromisoformat(task["initial_due"]))

def due_tasks(data, notified, today):
    result = []
    for task in data["tasks"]:
        if not task.get("enabled", True) or due_date(task) > today:
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
        watch = {"name": "Meow reminders"}
        item = {"title": task["name"] + " — due" + (" (overdue)" if due_date(task) < today else ""), "link": link}
        send_ntfy(os.environ["NTFY_TOPIC"], watch, item, link, action_label="Done")
        notified[task["id"]] = task.get("last_done") or "initial"
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
