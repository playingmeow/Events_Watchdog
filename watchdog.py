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
from difflib import SequenceMatcher
from html.parser import HTMLParser
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


class TelegramPosts(HTMLParser):
    """Extract public Telegram post text and permalinks without external packages."""
    def __init__(self):
        super().__init__()
        self.posts = []
        self.depth = 0
        self.collect = False
        self.text_depth = 0
        self.parts = []
        self.link = ""
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = a.get("class","").split()
        if "tgme_widget_message" in classes and a.get("data-post"):
            self.link = "https://t.me/" + a["data-post"]
        if "tgme_widget_message_text" in classes:
            self.collect = True
            self.text_depth = 1
            self.parts = []
        elif self.collect:
            self.text_depth += 1
        if "tgme_widget_message_date" in classes and a.get("href","").startswith("https://t.me/"):
            self.link = a["href"]
    def handle_endtag(self, tag):
        if self.collect:
            self.text_depth -= 1
            if self.text_depth == 0:
                self.collect = False
                body = " ".join(" ".join(self.parts).split())
                if body:
                    self.posts.append({"title":body[:180],"description":body,"link":self.link or "https://t.me/s/Heartbeatbedok","published":""})
                self.link = ""
    def handle_data(self, data):
        if self.collect:
            self.parts.append(data)

def telegram_feed(source):
    req = Request(source["url"],headers={"User-Agent":"Mozilla/5.0 EventsWatchdog/0.1"})
    with urlopen(req,timeout=12) as response:
        page = response.read(1500000).decode("utf-8","replace")
    parser = TelegramPosts()
    parser.feed(page)
    return parser.posts

def upcoming_event(item, today=None):
    """Accept dated events/notices until their last day, within a 60-day horizon."""
    current = today or datetime.now(SGT).date()
    body = item["description"]
    month_pattern = r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    months = {name.lower(): i for i, name in enumerate("January February March April May June July August September October November December".split(), 1)}

    def date_for(day, month, year=None):
        # Yearless dates in January/February may refer to next year.
        month_num = months[month.lower()]
        yr = int(year) if year else current.year
        if not year and month_num < current.month and current.month >= 10:
            yr += 1
        try:
            return datetime(yr, month_num, int(day)).date()
        except ValueError:
            return None

    dates = []
    # Ranges: "30 October to 8 November", "3–4 November", "3 and 4 November".
    cross_month = rf"\b(\d{{1,2}})\s+{month_pattern}\s*(?:to|[-–])\s*(\d{{1,2}})\s+{month_pattern}\s*(20\d{{2}})?\b"
    for m in re.finditer(cross_month, body, re.I):
        dates.append(date_for(m.group(3), m.group(4), m.group(5)))
    same_month = rf"\b\d{{1,2}}\s*(?:to|[-–]|and)\s*(\d{{1,2}})\s+{month_pattern}\s*(20\d{{2}})?\b"
    for m in re.finditer(same_month, body, re.I):
        dates.append(date_for(m.group(1), m.group(2), m.group(3)))
    singles = rf"\b(\d{{1,2}})\s+{month_pattern}\s*(20\d{{2}})?\b"
    for m in re.finditer(singles, body, re.I):
        dates.append(date_for(m.group(1), m.group(2), m.group(3)))
    # For a multi-day range, a past start must not override its future end.
    return any(d is not None and current <= d <= current + timedelta(days=60) for d in dates)

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

def same_oth_notice(a, b):
    """Conservatively merge near-identical OTH announcements across channels."""
    def cleaned(item):
        return " ".join(re.findall(r"[a-z0-9]+", item["description"].lower()))
    left, right = cleaned(a), cleaned(b)
    return min(len(left),len(right)) >= 70 and SequenceMatcher(None,left,right).ratio() >= 0.92

def already_seen_event(item, history):
    """Recognise OTH reposts across weekly runs, including other channels."""
    return any(same_oth_notice(item, {"description":entry["text"]}) for entry in history)

def remember_event(item, history, today):
    if not already_seen_event(item, history):
        history.append({"text":item["description"], "date":today.isoformat()})

def dismissed_event(item, watch, feedback):
    """Dismiss a particular event, not its venue or future unrelated sessions."""
    entries = feedback.get(watch["id"], [])
    key = story_key(item, watch)
    for entry in entries:
        if entry.get("key") == key:
            return True
        if watch["id"] == "our-tampines-hub" and entry.get("text"):
            if same_oth_notice(item, {"description":entry["text"]}):
                return True
    return False

def add_candidate(candidates, item, watch):
    if watch["id"] == "our-tampines-hub":
        if any(same_oth_notice(item, existing) for existing in candidates.values()):
            return False
    key = hashlib.sha256(story_key(item,watch).encode()).hexdigest()[:24]
    if key in candidates:
        return False
    candidates[key] = item
    return True

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
    state.setdefault("oth_history",[])
    feedback_path = ROOT/"feedback.json"
    feedback = json.loads(feedback_path.read_text()) if feedback_path.exists() else {}
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
                feed_items = telegram_feed(source) if source['type'] == 'telegram_public' else get_feed(source)
                fetched += len(feed_items)
                matched = 0
                for item in feed_items:
                    timely = upcoming_event(item) if source["type"] == "telegram_public" else fresh(item, max_age_days=watch.get("max_age_days",14))
                    if watch["id"] == "our-tampines-hub":
                        timely = timely and upcoming_event(item)
                    if timely and (source["type"] == "telegram_public" or relevant(item,watch)):
                        matched += 1
                        add_candidate(candidates,item,watch)
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
        history = state["oth_history"] if watch["id"] == "our-tampines-hub" else []
        baseline = watch["id"] not in state["initialised"]
        for key,item in candidates.items():
            if key in seen or dismissed_event(item, watch, feedback) or (watch["id"] == "our-tampines-hub" and already_seen_event(item, history)):
                continue
            if dry_run:
                print("[DRY RUN]",watch["name"],item["title"],item["link"])
            elif not baseline:
                send_ntfy(os.environ["NTFY_TOPIC"],watch,item)
                total += 1
            if not dry_run:
                seen[key] = now.isoformat()
                if watch["id"] == "our-tampines-hub":
                    remember_event(item, history, now)
        if not dry_run:
            if baseline:
                state["initialised"].append(watch["id"])
            cutoff = (now-timedelta(days=365)).isoformat()
            state["seen"][watch["id"]] = {k:v for k,v in seen.items() if v >= cutoff}
    if not dry_run:
        cutoff = (now-timedelta(days=365)).isoformat()
        state["oth_history"] = [entry for entry in state["oth_history"] if entry["date"] >= cutoff]
        state_path.write_text(json.dumps(state,indent=2,sort_keys=True)+"\n")
    print("Notifications sent:",total)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run",action="store_true")
    args = p.parse_args()
    if not args.dry_run and not os.getenv("NTFY_TOPIC"):
        raise SystemExit("NTFY_TOPIC secret required for live mode")
    run(args.dry_run)
