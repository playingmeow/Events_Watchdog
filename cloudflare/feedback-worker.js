// Events Watchdog feedback endpoint (Cloudflare Worker).
// Secret: GITHUB_TOKEN (contents:read/write). Event IDs are not authentication.
// Deploy separately from the NLB worker. No GitHub token is exposed to the browser.
const REPO = "playingmeow/Events_Watchdog";
const FILE = "feedback.json";
const WATCHES = new Set(["heartbeat-bedok", "our-tampines-hub"]);
const encoder = new TextEncoder();

function response(body, status = 200, type = "text/html; charset=utf-8") {
  return new Response(body, { status, headers: { "content-type": type, "cache-control": "no-store", "x-content-type-options": "nosniff", "referrer-policy": "no-referrer" } });
}
function decodeBase64(value) {
  return Uint8Array.from(atob(value.replace(/\n/g, "")), c => c.charCodeAt(0));
}
function encodeBase64(bytes) {
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary);
}
async function github(env, method, body, sha) {
  const url = "https://api.github.com/repos/" + REPO + "/contents/" + FILE;
  const headers = { "authorization": "Bearer " + env.GITHUB_TOKEN, "accept": "application/vnd.github+json", "user-agent": "Events-Watchdog-Feedback", "x-github-api-version": "2022-11-28" };
  if (method === "PUT") headers["content-type"] = "application/json";
  const r = await fetch(url, { method, headers, body: body ? JSON.stringify({ message: "chore: record Not Interested feedback", content: encodeBase64(encoder.encode(JSON.stringify(body, null, 2) + "\n")), sha }) : undefined });
  if (!r.ok) throw new Error("GitHub update failed: " + r.status);
  return r.json();
}
export default {
  async fetch(request, env) {
    if (!env.GITHUB_TOKEN) return response("Not configured", 503, "text/plain");
    const url = new URL(request.url);
    if (url.pathname !== "/dismiss") return response("Not found", 404, "text/plain");
    const watch = url.searchParams.get("watch") || "";
    const key = url.searchParams.get("key") || "";
    if (!WATCHES.has(watch) || !/^[a-f0-9]{24}$/.test(key)) return response("Invalid link", 400, "text/plain");
    if (request.method === "GET") {
      return response('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Events Watchdog</title><h2>Not Interested?</h2><p>This will hide future alerts about this specific event.</p><form method="POST"><button type="submit">Confirm Not Interested</button></form>');
    }
    if (request.method !== "POST") return response("Method not allowed", 405, "text/plain");
    try {
      const stateUrl = "https://api.github.com/repos/" + REPO + "/contents/state.json";
      const stateRes = await fetch(stateUrl, { headers: { authorization: "Bearer " + env.GITHUB_TOKEN, accept: "application/vnd.github+json", "user-agent": "Events-Watchdog-Feedback" } });
      if (!stateRes.ok) throw new Error("Could not read event catalog");
      const stateFile = await stateRes.json();
      const state = JSON.parse(new TextDecoder().decode(decodeBase64(stateFile.content)));
      const catalog = state.event_catalog?.[watch]?.[key];
      if (!catalog || typeof catalog.text !== "string") return response("Event not recorded yet. Please try later.", 404, "text/plain");
      for (let attempt = 0; attempt < 3; attempt++) {
        const file = await github(env, "GET");
        const feedback = JSON.parse(new TextDecoder().decode(decodeBase64(file.content)));
        const entries = feedback[watch] ||= [];
        if (entries.some(e => e.key === catalog.story_key)) return response("<h2>Already marked Not Interested</h2>");
        entries.push({ key: catalog.story_key, text: catalog.text, date: new Date().toISOString().slice(0, 10) });
        try {
          await github(env, "PUT", feedback, file.sha);
          return response("<h2>Saved!</h2><p>You will not be notified again about this event.</p>");
        } catch (err) {
          if (attempt === 2 || !String(err).includes("409")) throw err;
        }
      }
    } catch (err) {
      return response("Could not save feedback. Please try again later.", 503, "text/plain");
    }
  }
};
