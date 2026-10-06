import unittest

from server import _event_evidence_metrics


def article(article_id, title, domain, source_id=None, tier="publisher"):
    return {
        "id": article_id,
        "source_id": source_id or article_id,
        "title": title,
        "description": "",
        "domain": domain,
        "tier": tier,
        "reliability": 0.7,
        "source_provider": domain,
    }


def update(article_id, observed_at, note):
    return {"article_id": article_id, "observed_at": observed_at, "note": note}


class EventEvidenceMetricsTests(unittest.TestCase):
    def setUp(self):
        self.now = 100_000.0
        self.first_seen = self.now - 3600

    def metrics(self, articles, updates, first_seen=None, at=None):
        return _event_evidence_metrics(
            articles,
            updates,
            self.now if at is None else at,
            self.first_seen if first_seen is None else first_seen,
        )

    def test_repeated_observation_of_one_article_is_one_development(self):
        row = article("article-1", "Central bank announces new policy framework", "news.example")
        repeated = [
            update("article-1", self.now - 300, "Central bank announces new policy framework"),
            update("article-1", self.now - 200, "Central bank announces new policy framework"),
            update("article-1", self.now - 100, "Central bank announces new policy framework"),
        ]
        result = self.metrics([row], repeated)
        self.assertEqual(result["recent_developments"], 1)
        self.assertEqual(result["independent_sources"], 1)
        self.assertEqual(result["velocity"], 1.0)

    def test_distinct_articles_covering_same_event_add_evidence(self):
        rows = [
            article("article-1", "Central bank announces new policy framework", "one.example"),
            article("article-2", "Banks prepare for effects of central bank policy", "two.example"),
        ]
        updates = [
            update("article-1", self.now - 400, "Central bank announces new policy framework"),
            update("article-2", self.now - 200, "Banks prepare for effects of central bank policy"),
        ]
        result = self.metrics(rows, updates)
        self.assertEqual(len(result["families"]), 2)
        self.assertEqual(result["recent_developments"], 2)
        self.assertEqual(result["independent_sources"], 2)

    def test_multiple_independent_publishers_raise_corroboration(self):
        rows = [
            article("article-1", "Parliament passes national energy bill", "one.example"),
            article("article-2", "Energy companies assess new law impact", "two.example"),
            article("article-3", "Regional utilities announce compliance plans", "three.example"),
        ]
        result = self.metrics(rows, [])
        corroboration = min(1.0, max(0, result["independent_sources"] - 1) / 4)
        self.assertEqual(result["independent_sources"], 3)
        self.assertEqual(corroboration, 0.5)

    def test_syndicated_copy_on_another_url_is_one_evidence_source(self):
        title = "Central bank announces new policy framework for lending"
        rows = [
            article("article-1", title, "publisher-one.example"),
            article("article-2", "Central bank: announces new policy framework for lending", "publisher-two.example"),
        ]
        updates = [
            update("article-1", self.now - 300, title),
            update("article-2", self.now - 100, title),
        ]
        result = self.metrics(rows, updates)
        self.assertEqual(len(result["families"]), 1)
        self.assertEqual(result["independent_sources"], 1)
        self.assertEqual(result["recent_developments"], 1)

    def test_velocity_tracks_distinct_recent_activity_and_ages_out(self):
        row = article("article-1", "Election commission announces nationwide voting schedule", "news.example")
        rows = [
            update("article-1", self.now - 5 * 3600, "Election commission announces nationwide voting schedule"),
            update("article-1", self.now - 3600, "Election commission confirms regional voting dates and revised polling hours"),
            update("article-1", self.now - 8 * 3600, "Election commission opens registration for eligible voters"),
        ]
        started = self.now - 10 * 3600
        result = self.metrics([row], rows, first_seen=started)
        self.assertEqual(result["recent_developments"], 2)
        self.assertAlmostEqual(result["velocity"], 0.2)

        later = self.metrics([row], rows, first_seen=started, at=self.now + 2 * 3600)
        self.assertEqual(later["recent_developments"], 1)
        self.assertAlmostEqual(later["velocity"], 1 / 12)
        self.assertLess(later["velocity"], result["velocity"])


if __name__ == "__main__":
    unittest.main()
