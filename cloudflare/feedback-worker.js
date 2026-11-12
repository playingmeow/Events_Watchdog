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

function awayPreview(today) {
  const tomorrow = new Date(Date.parse(today + "T00:00:00Z") + 86400000).toISOString().slice(0,10);
  return `<section><h2>Away-period preview</h2>
    <p>Enter the padded start and end in Singapore time. This preview only highlights clashes.</p>
    <label>From <input type="datetime-local" id="away-start"></label>
    <label>Until <input type="datetime-local" id="away-end"></label>
    <button type="button" id="test-away" data-day="${tomorrow}">Test with tomorrow</button>
    <details><summary>Add a second trip</summary>
      <label>From <input type="datetime-local" id="away-start-2"></label>
      <label>Until <input type="datetime-local" id="away-end-2"></label>
    </details>
    <button type="button" id="save-trips">Save trips</button>
    <p id="away-result" role="status"></p></section>
    <style>.trip-clash{color:#a41123;font-weight:bold}</style>
    <script>
      document.addEventListener("DOMContentLoaded", () => {
        const start = document.getElementById("away-start");
        const end = document.getElementById("away-end");
        const result = document.getElementById("away-result");
        const test = document.getElementById("test-away");
        const inputs = [[start, end], [document.getElementById("away-start-2"), document.getElementById("away-end-2")]];
        const storageKey = "meow-away-trips";
        const rangesFromInputs = () => inputs.map(([from, to]) => [from.value, to.value]);
        let sample;
        function highlight(ranges = rangesFromInputs()) {
          const valid = ranges.filter(([from, to]) => from && to && from < to);
          const invalid = ranges.some(([from, to]) => from && to && from >= to);
          let count = 0;
          for (const row of document.querySelectorAll("[data-home-alert]")) {
            const alert = row.dataset.homeAlert;
            const clash = Boolean(alert && valid.some(([from, to]) => from <= alert && alert < to));
            const cell = row.cells[1];
            cell.classList.toggle("trip-clash", clash);
            cell.querySelector(".trip-label")?.remove();
            if (clash) {
              const label = document.createElement("span");
              label.className = "trip-label";
              label.textContent = " · Overlaps trip";
              cell.append(label);
              count++;
            }
          }
          result.textContent = (valid.length ? count + " home-only reminder(s) overlap. " : "") +
            (invalid ? "Each trip must end after it starts." : "");
        }
        function update() {
          sample?.remove();
          sample = undefined;
          highlight();
        }
        for (const input of inputs.flat()) input.addEventListener("input", update);
        try {
          const saved = JSON.parse(localStorage.getItem(storageKey) || "[]");
          inputs.forEach(([from, to], index) => {
            if (Array.isArray(saved[index])) {
              [from.value, to.value] = saved[index];
              if (index === 1 && from.value && to.value) from.closest("details").open = true;
            }
          });
        } catch {
          // The preview remains usable when browser storage is unavailable.
        }
        highlight();
        document.getElementById("save-trips").addEventListener("click", () => {
          const ranges = rangesFromInputs();
          if (ranges.some(([from, to]) => (from || to) && (!from || !to || from >= to))) {
            result.textContent = "Enter a start and a later end for each trip you want to save.";
            return;
          }
          try {
            localStorage.setItem(storageKey, JSON.stringify(ranges));
            update();
            result.textContent += " Trips saved in this browser.";
          } catch {
            result.textContent = "This browser could not save the trip dates.";
          }
        });
        test.addEventListener("click", () => {
          const day = test.dataset.day;
          sample?.remove();
          sample = document.querySelector("table").insertRow(1);
          sample.dataset.homeAlert = day + "T09:30";
          for (const value of ["Sample robot roller check", "Next " + day + " at 9:30 AM", "Test only", ""]) {
            sample.insertCell().textContent = value;
          }
          highlight([[day + "T00:00", day + "T23:59"]]);
          result.textContent = "Sample preview for tomorrow. " + result.textContent;
        });
      });
    </script>`;
}

async function dashboard(env) {
  const api = "https://api.github.com/repos/" + REPO + "/contents/maintenance.json";
  const r = await fetch(api, {headers:{authorization:"Bearer "+env.GITHUB_TOKEN,accept:"application/vnd.github+json","user-agent":"Meow-Dashboard"}});
  if (!r.ok) return response("Dashboard unavailable",503,"text/plain");
  const file = await r.json();
  const data = JSON.parse(new TextDecoder().decode(decodeBase64(file.content)));
  const today = new Date(Date.now()+8*3600000).toISOString().slice(0,10);
  const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  const days = (a,b) => Math.round((Date.parse(a+"T00:00:00Z")-Date.parse(b+"T00:00:00Z"))/86400000);
  const rows = data.tasks.filter(t=>t.enabled!==false).map(t=>{
    let due,summary;
    let frequency = t.interval_days ? `Every ${t.interval_days} ${t.interval_days === 1 ? "day" : "days"}` : "Once";
    if(t.kind==="daily"){
      frequency="Daily";
      due=t.initial_due;
      const elapsed=Math.max(0,days(today,due)+1);
      const taken=(t.completed_dates||[]).filter(d=>d>=due&&d<=today).length;
      summary=elapsed ? taken+"/"+elapsed+" days ("+Math.round(taken/elapsed*100)+"%)" : "Starts "+due;
      due=today;
    }else if(t.kind==="monthly_day"){
      const day=t.day_of_month;
      frequency="Monthly (day "+day+")";
      const current=today.slice(0,8)+String(day).padStart(2,"0");
      const prev=new Date(Date.parse(today.slice(0,8)+"01T00:00:00Z"));
      prev.setUTCMonth(prev.getUTCMonth()-1);
      const previous=prev.toISOString().slice(0,8)+String(day).padStart(2,"0");
      const cycle=current<=today?current:previous;
      due=cycle<t.initial_due?t.initial_due:cycle;
      summary="Completed cycles: "+(t.completed_cycles||[]).length;
      if(cycle>=t.initial_due && (t.completed_cycles||[]).includes(cycle)) summary+="; current cycle done";
    }else{
      due=t.last_done&&t.interval_days ? new Date(Date.parse(t.last_done+"T00:00:00Z")+t.interval_days*86400000).toISOString().slice(0,10) : t.initial_due;
      const h=t.history||[];
      summary=h.length+" completions; "+h.filter(x=>x.days_late===0).length+" on time; "+h.reduce((s,x)=>s+(x.days_late||0),0)+" late days";
    }
    const monthlyDone=t.kind==="monthly_day" && (t.completed_cycles||[]).includes(due);
    const status=monthlyDone ? "Done this cycle" : t.kind==="daily" && today<t.initial_due ? "Starts "+t.initial_due : t.kind==="daily"&&(t.completed_dates||[]).includes(today) ? "Done today" : due<=today ? "Due / overdue" : "Next "+due;
    const homeOnly = /^(princess-antiflea|honey-antiflea|dust-bag)$/.test(t.id) ||
      /roller|hepa filter|fan cleaning|clean.*fan|clean sensors|brush wear/i.test(t.name);
    const alertDate = due < today ? today : due;
    const alert = homeOnly && /^\d{4}-\d{2}-\d{2}$/.test(alertDate) ? alertDate + "T09:30" : "";
    return '<tr data-home-alert="'+alert+'"><td>'+esc(t.name)+'</td><td>'+esc(status)+"</td><td>"+esc(frequency)+"</td><td>"+esc(summary)+"</td></tr>";
  }).join("");
  return response('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Meow Accountability</title><style>body{font:16px system-ui;max-width:850px;margin:32px auto;padding:0 16px}table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #ddd;text-align:left}</style><h1>Meow Accountability</h1><p>Today: '+today+'</p>'+awayPreview(today)+'<table><tr><th>Task</th><th>Status</th><th>Frequency</th><th>History</th></tr>'+rows+'</table><p><small>Daily completion is counted only when Done is tapped; it does not prove consumption.</small></p>');
}

async function maintenanceDone(request, env, url) {
  const taskId = url.searchParams.get("task") || "";
  if (!/^[a-z0-9-]{1,40}$/.test(taskId)) return response("Invalid task", 400, "text/plain");
  const api = "https://api.github.com/repos/" + REPO + "/contents/maintenance.json";
  const headers = { authorization: "Bearer " + env.GITHUB_TOKEN, accept: "application/vnd.github+json",
    "user-agent": "Events-Watchdog-Maintenance", "x-github-api-version": "2022-11-28" };
  async function load() {
    const res = await fetch(api, { headers });
    if (!res.ok) throw new Error("Maintenance read failed: " + res.status);
    const file = await res.json();
    return { sha: file.sha, data: JSON.parse(new TextDecoder().decode(decodeBase64(file.content))) };
  }
  try {
    if (request.method === "GET") {
      const { data } = await load();
      const task = data.tasks.find(t => t.id === taskId);
      if (!task) return response("Unknown task", 404, "text/plain");
      const safeName = task.name.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      return response('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Maintenance</title><h2>Mark maintenance done?</h2><p>' + safeName + '</p><form method="POST"><button type="submit">Confirm Done</button></form>');
    }
    if (request.method !== "POST") return response("Method not allowed", 405, "text/plain");
    for (let attempt = 0; attempt < 3; attempt++) {
      const { sha, data } = await load();
      const task = data.tasks.find(t => t.id === taskId);
      if (!task) return response("Unknown task", 404, "text/plain");
      const today = new Date(Date.now() + 8 * 3600000).toISOString().slice(0, 10);
      if (task.kind === "monthly_day") {
        const cycle = url.searchParams.get("cycle") || "";
        const day = task.day_of_month;
        const current = today.slice(0,8) + String(day).padStart(2,"0");
        const prev = new Date(Date.parse(today.slice(0,8)+"01T00:00:00Z"));
        prev.setUTCMonth(prev.getUTCMonth()-1);
        const previous = prev.toISOString().slice(0,8)+String(day).padStart(2,"0");
        const active = current <= today ? current : previous;
        if (active < task.initial_due || cycle !== active) return response("This reminder belongs to an old or inactive cycle.",409,"text/plain");
        task.completed_cycles ||= [];
        if (task.completed_cycles.includes(cycle)) return response("<h2>Already Done for this cycle!</h2>");
        task.completed_cycles.push(cycle);
        task.history ||= [];
        task.history.push({done:today,due:cycle,days_late:Math.max(0,Math.round((Date.parse(today+"T00:00:00Z")-Date.parse(cycle+"T00:00:00Z"))/86400000))});
      } else if (task.kind === "daily") {
        task.completed_dates ||= [];
        if (task.completed_dates.includes(today)) return response("<h2>Already marked Done today!</h2>");
        task.completed_dates.push(today);
      } else {
        if (task.last_done === today) return response("<h2>Already marked Done today!</h2>");
        const due = task.last_done && task.interval_days ? new Date(Date.parse(task.last_done + "T00:00:00Z") + task.interval_days * 86400000).toISOString().slice(0,10) : task.initial_due;
        task.history ||= [];
        task.history.push({done:today, due, days_late:Math.max(0,Math.round((Date.parse(today+"T00:00:00Z")-Date.parse(due+"T00:00:00Z"))/86400000))});
        task.last_done = today;
      }
      const payload = { message: "chore: complete maintenance " + taskId,
        content: encodeBase64(encoder.encode(JSON.stringify(data, null, 2) + "\n")), sha };
      const result = await fetch(api, { method: "PUT",
        headers: { ...headers, "content-type": "application/json" }, body: JSON.stringify(payload) });
      if (result.ok) return response(task.kind==="monthly_day" ? "<h2>Saved!</h2><p>No more nags until the next scheduled cycle.</p>" : "<h2>Saved!</h2><p>Countdown restarted from today.</p>");
      if (result.status !== 409 && result.status !== 422) throw new Error("Maintenance update failed: " + result.status);
    }
    throw new Error("Concurrent updates");
  } catch (err) {
    return response("Could not save maintenance. Please try again later.", 503, "text/plain");
  }
}

export default {
  async fetch(request, env) {
    if (!env.GITHUB_TOKEN) return response("Not configured", 503, "text/plain");
    const url = new URL(request.url);
    if (url.pathname === "/dashboard" && request.method === "GET") return dashboard(env);
    if (url.pathname === "/maintenance/done") return maintenanceDone(request, env, url);
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

// Production deploys from main through Cloudflare Workers Builds.
