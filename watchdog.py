"""Lightweight public-news discovery → relevance → dedupe → ntfy."""
import argparse
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
SGT = timezone(timedelta(hours=8))

def normalise_url(url):
    p = urlsplit(url.strip())
    q = [(k,v) for k,v in parse_qsl(p.query) if not (k.lower().startswith("utm_") or k.lower() in ("fbclid","gclid"))]
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip("/"),urlencode(q),""))

def rss_url(source):
    q = quote(source["query"])
    if source["type"] == "google_news_rss":
        return f"https://news.google.com/rss/search?q={q}&hl=en-SG&gl=SG&ceid=SG:en"
    if source["type"] == "bing_news_rss":
        return f"https://www.bing.com/news/search?q={q}&format=rss"
    raise ValueError("Unsupported source")

def get_feed(source):
    req = Request(rss_url(source),headers={"User-Agent":"Mozilla/5.0 EventsWatchdog/0.1"})
    with urlopen(req,timeout=12) as response:
        data = response.read(1500000)
    root = ET.fromstring(data)
    items = []
    for node in root.findall(".//item")[:30]:
        title = html.unescape(node.findtext("title","").strip())
        link = html.unescape(node.findtext("link","").strip())
        desc = re.sub(r"<[^>]*>"," ",html.unescape(node.findtext("description","")))[:600]
        published = node.findtext("pubDate","").strip()
        if title and link.startswith(("https://","http://")):
            items.append({"title":title,"link":link,"description":desc,"published":published})
    return items

def fresh(item, now=None, max_age_days=14):
    """Reject undated, stale and implausibly future-dated RSS entries."""
    try:
        published = parsedate_to_datetime(item["published"])
        if published.tzinfo is None:
            return False
        current = now or datetime.now(timezone.utc)
        age = current.astimezone(timezone.utc) - published.astimezone(timezone.utc)
        return timedelta(0) <= age <= timedelta(days=max_age_days)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False

def relevant(item,watch):
    content = (item["title"]+" "+item["description"]).lower()
    keywords = watch.get("keywords",[])
    if not any(k.lower() in content for k in keywords):
        return False
    if watch.get("type") == "event":
        return True
    words = watch.get("deal_words",["promotion","promo","sale","offer","discount","anniversary","deal","fare"])
    return any(w.lower() in content for w in words)

def story_key(item, watch):
    """Group coverage of the same named campaign, while retaining distinct bank offers."""
    title = item["title"].lower()
    try:
        period = parsedate_to_datetime(item["published"]).strftime("%Y-%m")
    except (KeyError, TypeError, ValueError):
        period = "unknown"
    if watch["id"] == "sq-time-to-fly":
        if any(x in title for x in ("citi prestige","hsbc","dbs","uob","amex","ocbc")):
            bank = next(x for x in ("citi prestige","hsbc","dbs","uob","amex","ocbc") if x in title)
            return "bank:"+bank+":"+period
        if "time to fly" in title or "380,000" in title:
            return "campaign:time-to-fly:"+period
    return "url:"+normalise_url(item["link"])

def send_ntfy(topic,watch,item):
    server = (os.getenv("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
    headers = {"Title":"Watchdog: "+watch["name"],"Click":item["link"],"Tags":"mag","Content-Type":"text/plain; charset=utf-8"}
    token = os.getenv("NTFY_TOKEN")
    if token:
        headers["Authorization"] = "Bearer "+token
    body = item["title"]+"\n\n"+item["link"]+"\n\nCheck official dates, availability and conditions."
    req = Request(server+"/"+quote(topic,safe=""),data=body.encode(),headers=headers,method="POST")
    with urlopen(req,timeout=12) as response:
        response.read()

def run(dry_run=False):
    watches = json.loads((ROOT/"watchlist.json").read_text())["watches"]
    state_path = ROOT/"state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"seen":{},"initialised":[]}
    state.setdefault("seen",{})
    state.setdefault("initialised",[])
    now = datetime.now(SGT).date()
    total = 0
    for watch in watches:
        if watch.get("enabled",True) is False:
            continue
        sources = watch.get("sources",[])
        if not sources:
            print("WARNING: No sources configured for",watch["name"])
            continue
        candidates = {}
        success = 0
        fetched = 0
        for source in sources:
            try:
                feed_items = get_feed(source)
                fetched += len(feed_items)
                matched = 0
                for item in feed_items:
                    if relevant(item,watch) and fresh(item, max_age_days=watch.get("max_age_days",14)):
                        matched += 1
                        key = hashlib.sha256(story_key(item,watch).encode()).hexdigest()[:24]
                        candidates.setdefault(key,item)
                print(f"[SOURCE] {watch['id']} {source['type']}: fetched={len(feed_items)} matched={matched}")
                if matched == 0:
                    for sample in feed_items[:3]:
                        print("[SAMPLE]",watch["id"],sample["title"][:160])
                success += 1
            except Exception as exc:
                print("WARNING:",watch["name"],source["type"],str(exc),file=sys.stderr)
        print(f"[SUMMARY] {watch['id']}: sources_ok={success}/{len(sources)} fetched={fetched} unique_matches={len(candidates)}")
        if success == 0:
            print("WARNING: All feeds failed for",watch["name"])
            continue
        seen = state["seen"].setdefault(watch["id"],{})
        baseline = watch["id"] not in state["initialised"]
        for key,item in candidates.items():
            if key in seen:
                continue
            if dry_run:
                print("[DRY RUN]",watch["name"],item["title"],item["link"])
            elif not baseline:
                send_ntfy(os.environ["NTFY_TOPIC"],watch,item)
                total += 1
            if not dry_run:
                seen[key] = now.isoformat()
        if not dry_run:
            if baseline:
                state["initialised"].append(watch["id"])
            cutoff = (now-timedelta(days=365)).isoformat()
            state["seen"][watch["id"]] = {k:v for k,v in seen.items() if v >= cutoff}
    if not dry_run:
        state_path.write_text(json.dumps(state,indent=2,sort_keys=True)+"\n")
    print("Notifications sent:",total)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run",action="store_true")
    args = p.parse_args()
    if not args.dry_run and not os.getenv("NTFY_TOPIC"):
        raise SystemExit("NTFY_TOPIC secret required for live mode")
    run(args.dry_run)
