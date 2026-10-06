import unittest

from server import (
    INDIA_RELEVANCE_THRESHOLD,
    WORLD_RELEVANCE_THRESHOLD,
    _india_relevance_assessment,
    _world_consequence_assessment,
)


class RelevanceLensTests(unittest.TestCase):
    def test_publisher_country_and_language_are_only_weak_support(self):
        result = _india_relevance_assessment(
            {"title": "A technology company announces a new device", "topic": "Technology"},
            articles=[{"country": "IN", "language": "hi"}],
        )
        self.assertEqual(result["direct"], 0.0)
        self.assertEqual(result["material"], 0.0)
        self.assertEqual(result["score"], 0.12)
        self.assertLess(result["score"], INDIA_RELEVANCE_THRESHOLD)

    def test_direct_india_event_does_not_require_an_indian_publisher(self):
        result = _india_relevance_assessment(
            {"title": "India announces a new national policy", "topic": "Politics"},
            articles=[{"country": "US", "language": "en"}],
        )
        self.assertGreaterEqual(result["direct"], INDIA_RELEVANCE_THRESHOLD)
        self.assertEqual(result["publisher"], 0.0)

    def test_country_mention_in_a_quote_is_weak_without_event_evidence(self):
        result = _india_relevance_assessment(
            {"title": "Actor says he cannot feel peace in India anymore", "topic": "Entertainment"},
        )
        self.assertEqual(result["direct"], 0.0)
        self.assertEqual(result["weak_mention"], 0.12)
        self.assertLess(result["score"], INDIA_RELEVANCE_THRESHOLD)

    def test_explicit_global_consequence_for_india_is_material_relevance(self):
        result = _india_relevance_assessment(
            {"title": "Global energy prices shift", "topic": "Energy"},
            articles=[{"title": "Import costs rise", "description": "India relies on these imports for energy supply."}],
        )
        self.assertEqual(result["direct"], 0.0)
        self.assertGreaterEqual(result["material"], INDIA_RELEVANCE_THRESHOLD)

    def test_unrelated_india_mention_and_market_term_do_not_create_material_relevance(self):
        result = _india_relevance_assessment(
            {"title": "US removes bombers from a British air base", "topic": "Geopolitics"},
            articles=[{"description": "India held routine talks last month. US bombers were redeployed to their home stations."}],
        )
        self.assertEqual(result["material"], 0.0)
        self.assertLess(result["score"], INDIA_RELEVANCE_THRESHOLD)

    def test_publisher_suffix_is_not_direct_event_evidence(self):
        result = _india_relevance_assessment(
            {"title": "A technology company announces a new device - The Indian Express", "topic": "Technology"},
            articles=[{"source_name": "The Indian Express RSS", "country": "IN", "language": "en"}],
        )
        self.assertEqual(result["direct"], 0.0)
        self.assertLess(result["score"], INDIA_RELEVANCE_THRESHOLD)

    def test_unlisted_publisher_suffix_is_not_direct_india_evidence(self):
        result = _india_relevance_assessment(
            {
                "title": "A global event has consequences - The Times of India",
                "entities": '["The Times", "India"]',
                "locations": '["The Times", "India"]',
                "topic": "World",
            },
            articles=[{"source_name": "Google News India"}],
            source_names="Google News India",
        )
        self.assertEqual(result["direct"], 0.0)
        self.assertLess(result["score"], INDIA_RELEVANCE_THRESHOLD)

    def test_world_assessment_depends_on_event_consequence_not_source_country(self):
        event = {
            "title": "International security agreement reaches a major turning point",
            "topic": "Geopolitics",
            "geopolitical_relevance": 0.9,
            "significance": 0.8,
            "corroboration": 0.6,
            "authority": 0.5,
            "urgency": 0.4,
            "velocity": 0.5,
        }
        assessed = _world_consequence_assessment(event)
        self.assertTrue(assessed["significant"])
        self.assertGreaterEqual(assessed["score"], WORLD_RELEVANCE_THRESHOLD)

    def test_world_assessment_can_recover_geopolitical_evidence_under_a_wrong_topic_label(self):
        assessed = _world_consequence_assessment(
            {
                "title": "US withdraws bombers from a UK base after an alleged terror plot",
                "topic": "Property",
                "significance": 0.7,
                "corroboration": 0.7,
                "authority": 0.6,
                "urgency": 0.3,
            },
            "Military security concerns followed an attack investigation.",
        )
        self.assertTrue(assessed["geopolitical_context"])
        self.assertTrue(assessed["significant"])

    def test_low_impact_local_story_does_not_become_world_by_default(self):
        assessed = _world_consequence_assessment({
            "title": "Local council changes parking rules",
            "topic": "Politics",
            "social_relevance": 0.2,
            "significance": 0.15,
            "corroboration": 0.0,
            "authority": 0.1,
        })
        self.assertFalse(assessed["significant"])

    def test_an_india_event_can_also_be_globally_consequential(self):
        india = _india_relevance_assessment({"title": "India and global partners reach a major climate agreement"})
        world = _world_consequence_assessment({
            "title": "India and global partners reach a major climate agreement",
            "topic": "Geopolitics",
            "geopolitical_relevance": 0.9,
            "significance": 0.8,
            "corroboration": 0.5,
            "authority": 0.5,
        })
        self.assertGreaterEqual(india["score"], INDIA_RELEVANCE_THRESHOLD)
        self.assertTrue(world["significant"])


if __name__ == "__main__":
    unittest.main()
