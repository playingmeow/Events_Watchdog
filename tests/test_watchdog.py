import unittest
from watchdog import normalise_url, relevant, rss_url

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

    def test_rss_url(self):
        self.assertIn("news.google.com",rss_url({"type":"google_news_rss","query":"test"}))

if __name__ == "__main__":
    unittest.main()
