"""Manual Hirosaki ntfy delivery test. Never changes maintenance or deduplication state."""
import json
import os
from urllib.parse import quote
from urllib.request import Request, urlopen
from watchdog import ROOT

def main():
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        raise SystemExit("NTFY_TOPIC secret is missing; no notification sent")
    data = json.loads((ROOT / "maintenance.json").read_text())
    task = next(t for t in data["tasks"] if t["id"] == "hirosaki-sakura-final-2027")
    if task["kind"] != "one_off" or task["initial_due"] != "2027-04-23":
        raise SystemExit("Hirosaki production reminder has changed; test aborted")
    base = os.environ.get("FEEDBACK_BASE_URL", "").rstrip("/")
    if not base.startswith("https://"):
        raise SystemExit("FEEDBACK_BASE_URL is missing or insecure")
    server = (os.environ.get("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
    headers = {
        "Title": "[TEST ONLY] Hirosaki Sakura Festival - ntfy",
        "Tags": "test_tube",
        "Click": base + "/dashboard",
        "Content-Type": "text/plain; charset=utf-8",
    }
    if os.environ.get("NTFY_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["NTFY_TOKEN"]
    body = (
        "TEST ONLY — no action needed today.\\n"
        "The real Hirosaki reminder remains scheduled for 23 April 2027 at the daily run.\\n\\n"
        + task["message"]
        + "\\n\\nThis test does not update maintenance.json or state.json."
    )
    req = Request(server + "/" + quote(topic, safe=""), data=body.encode("utf-8"), headers=headers, method="POST")
    with urlopen(req, timeout=12) as response:
        response.read()
        print("ntfy accepted the Hirosaki test notification (HTTP " + str(response.status) + ")")
    print("No reminder or deduplication state was changed.")

if __name__ == "__main__":
    main()
