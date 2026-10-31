# Events Watchdog feedback worker (staged; not deployed)

This worker is **separate** from the existing NLB Cloudflare Worker.

## Safety
- The ntfy action will open a signed `/dismiss` URL.
- GET shows a confirmation form; **only POST saves feedback**.
- HMAC-SHA256 signed links expire. The signing secret is shared between GitHub Actions and this worker.
- GitHub API token remains a Cloudflare secret; never put it in a notification or repository.
- Only `heartbeat-bedok` and `our-tampines-hub` can be dismissed.
- The worker reads the exact event description from `state.json` and writes the dismissal to `feedback.json`.

## Remaining integration before deployment
1. Add a compact `event_catalog` to `state.json` for each **actually sent** event, including its 24-character notification key, story key, and original description.
2. Generate the signed ntfy action URL in Python, using `FEEDBACK_SECRET` and the worker's `FEEDBACK_BASE_URL`. Do not attach an action to promotions or operational notices without confirming desired behaviour.
3. Deploy this worker as a new Cloudflare Worker, with `GITHUB_TOKEN` (fine-grained, **Contents: read/write only** on this repo) and a random `FEEDBACK_SECRET`. Add matching `FEEDBACK_SECRET` and `FEEDBACK_BASE_URL` to GitHub Actions.
4. Verify GET does not change GitHub, POST writes only the selected event, and repeat POST is idempotent.
5. Verify the workflow suppresses the dismissed event on a later scan. Keep scheduled checks in dry-run until this passes.

**Do not enable live notifications yet.** The worker is currently only a staged source file, and the Python notification integration is not connected.
