import unittest
import json
from pathlib import Path
from datetime import datetime, date, timezone, timedelta
from watchdog import normalise_url, relevant, rss_url, fresh, add_candidate, upcoming_event, already_seen_event, remember_event, dismissed_event, feedback_allowed, feedback_url

class WatchdogTests(unittest.TestCase):
    def test_tracking_removed(self):
        self.assertEqual(normalise_url("https://EXAMPLE.com/a/?utm_source=x"),"https://example.com/a")
    def test_promo_relevance(self):
        w={"keywords":["yakiniku-go"],"deal_words":["promotion","sale"]}
        self.assertTrue(relevant({"title":"Yakiniku-GO sale","description":""},w))
        self.assertFalse(relevant({"title":"Yakiniku-GO opens new outlet","description":""},w))
    def test_event_relevance(self):
        w={"type":"event","keywords":["heartbeat@bedok"]}
        self.assertTrue(relevant({"title":"Heartbeat@Bedok workshop","description":""},w))
    def test_real_promo_headlines(self):
        yakiniku = {"keywords":["yakiniku-go","yakiniku go"],"deal_words":["promotion","promo","sale","offer","discount","anniversary","deal","fare","special"]}
        sq = {"keywords":["singapore airlines","time to fly"],"deal_words":yakiniku["deal_words"]}
        self.assertTrue(relevant({"title":"Yakiniku-GO to offer 50% OFF Set Meals from S$8.90","description":""},yakiniku))
        self.assertTrue(relevant({"title":"Singapore Airlines and Scoot to offer discounted tickets at Time To Fly Travel Fair 2026","description":""},sq))

    def test_freshness(self):
        now = datetime(2026,10,31,tzinfo=timezone.utc)
        self.assertTrue(fresh({"published":"Fri, 30 Oct 2026 12:00:00 GMT"},now))
        self.assertFalse(fresh({"published":"Mon, 01 Sep 2025 12:00:00 GMT"},now))
        self.assertFalse(fresh({"published":""},now))
        self.assertFalse(fresh({"published":"Sun, 01 Nov 2026 12:00:00 GMT"},now))

    def test_oth_cross_channel_duplicate_and_distinct_notice(self):
        watch = {"id":"our-tampines-hub"}
        candidates = {}
        a = {"title":"Notice","description":"Attention Tampines residents and hub visitors! The OTH Hawker Centre will be closed for spring cleaning on 3 and 4 November from 7am to 11pm. This is to ensure a clean and pleasant environment.","link":"https://t.me/OTHcommunity/676"}
        b = dict(a, link="https://t.me/OTHlifestyle/528", description=a["description"].replace("11pm.","11pm ."))
        different = dict(a,link="https://t.me/OTHsports/618",description="Attention Tampines residents! The OTH Netball Fiesta will be held on 8 November from 9am to 6pm. Register your team for a full day of exciting matches and friendly competition.")
        self.assertTrue(add_candidate(candidates,a,watch))
        self.assertFalse(add_candidate(candidates,b,watch))
        self.assertTrue(add_candidate(candidates,different,watch))
        self.assertEqual(len(candidates),2)

    def test_event_expiry_and_multi_day_ranges(self):
        item = lambda s: {"description":s}
        self.assertTrue(upcoming_event(item("Deepavali 30 October to 8 November 2026"),date(2026,11,5)))
        self.assertFalse(upcoming_event(item("Deepavali 30 October to 8 November 2026"),date(2026,11,9)))
        self.assertTrue(upcoming_event(item("Hawker Centre closed 3 and 4 November"),date(2026,11,4)))
        self.assertFalse(upcoming_event(item("Hawker Centre closed 3 and 4 November"),date(2026,11,5)))
        self.assertTrue(upcoming_event(item("Workshop 5 January"),date(2026,12,15)))
        self.assertFalse(upcoming_event(item("Workshop 5 January"),date(2027,1,6)))

    def test_oth_repost_across_runs(self):
        history = []
        original = {"description":"Attention Tampines residents and hub visitors! The OTH Hawker Centre will be closed for spring cleaning on 3 and 4 November from 7am to 11pm. This is to ensure a clean and pleasant environment."}
        repost = {"description":original["description"].replace("11pm.","11pm .")}
        other = {"description":"The OTH Netball Fiesta is happening on 8 November from 9am to 6pm. Join an exciting day of sports, games and friendly competition with your friends and family!"}
        remember_event(original,history,date(2026,10,31))
        self.assertTrue(already_seen_event(repost,history))
        self.assertFalse(already_seen_event(other,history))
        remember_event(repost,history,date(2026,11,1))
        self.assertEqual(len(history),1)

    def test_not_interested_is_event_specific(self):
        watch = {"id":"our-tampines-hub"}
        text = "Attention Tampines residents and hub visitors! The OTH Hawker Centre will be closed for spring cleaning on 3 and 4 November from 7am to 11pm. This is to ensure a clean and pleasant environment."
        feedback = {"our-tampines-hub":[{"text":text}]}
        repost = {"title":"Notice","description":text.replace("11pm.","11pm ."),"link":"https://t.me/OTHlifestyle/528","published":""}
        unrelated = {"title":"Netball","description":"The OTH Netball Fiesta will be held on 8 November. Register for an exciting day of games and friendly competition!","link":"https://t.me/OTHsports/618","published":""}
        self.assertTrue(dismissed_event(repost,watch,feedback))
        self.assertFalse(dismissed_event(unrelated,watch,feedback))

    def test_feedback_only_for_events_not_operational_notices(self):
        watch = {"id": "our-tampines-hub", "type": "event"}
        event = {"title": "Netball Fiesta", "description": "Join the games on 8 November"}
        notice = {"title": "Hawker centre spring cleaning", "description": "Closed for maintenance on 3 November"}
        self.assertTrue(feedback_allowed(watch, event))
        self.assertFalse(feedback_allowed(watch, notice))
        self.assertFalse(feedback_allowed({"id":"sq-time-to-fly", "type":"promotion"}, event))

    def test_saved_feedback_roundtrip_suppresses_exact_event(self):
        feedback = json.loads((Path(__file__).resolve().parents[1] / "feedback.json").read_text())
        watch = {"id": "heartbeat-bedok"}
        dummy = {"title": "[TEST ONLY] Not Interested button verification",
                 "description": "[TEST ONLY] Not Interested button verification. Not a real event.",
                 "link": "https://github.com/playingmeow/Events_Watchdog"}
        self.assertTrue(dismissed_event(dummy, watch, feedback))
        unrelated = dict(dummy, link="https://github.com/playingmeow/Events_Watchdog/issues/1")
        self.assertFalse(dismissed_event(unrelated, watch, feedback))

    def test_rss_url(self):
        self.assertIn("news.google.com",rss_url({"type":"google_news_rss","query":"test"}))

if __name__ == "__main__":
    unittest.main()
