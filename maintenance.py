"""Small maintenance countdown extension for Events_Watchdog."""
import json
import os
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote
from watchdog import ROOT, SGT, datetime, send_ntfy

def due_date(task):
    anchor = task.get("last_done")
    if anchor:
        return date.fromisoformat(anchor) + timedelta(days=task["interval_days"])
    return date.fromisoformat(task["initial_due"])

def due_tasks(data, notified, today):
    return [task for task in data["tasks"]
            if due_date(task) <= today and notified.get(task["id"]) != (task.get("last_done") or "initial")]

def run_maintenance(dry_run=False):
    path = ROOT / "maintenance.json"
    if not path.exists():
        return
    data = json.loads(path.read_text())
    state_path = ROOT / "state.json"
    state = json.loads(state_path.read_text())
    notified = state.setdefault("maintenance_notified", {})
    today = datetime.now(SGT).date()
    tasks = due_tasks(data, notified, today)
    print(f"[MAINTENANCE] due={len(tasks)}")
    for task in tasks:
        if dry_run:
            print("[DRY RUN MAINTENANCE]", task["name"])
            continue
        base = os.getenv("FEEDBACK_BASE_URL", "").rstrip("/")
        if not base.startswith("https://"):
            raise ValueError("FEEDBACK_BASE_URL is required for maintenance Done buttons")
        link = base + "/maintenance/done?task=" + quote(task["id"], safe="")
        watch = {"name": "A30 Pro maintenance"}
        item = {"title": task["name"] + " — due", "link": link}
        send_ntfy(os.environ["NTFY_TOPIC"], watch, item, link)
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
