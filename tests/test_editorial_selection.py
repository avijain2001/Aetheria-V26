import unittest

import server


def editorial_item(
    event_id,
    title,
    *,
    topic="World",
    significance=0.8,
    impact=0.7,
    india=0.0,
    world=0.0,
    development=0.0,
    last_seen=None,
    entities=None,
    financial=0.0,
    geopolitical=0.0,
    social=0.0,
    description="Evidence-backed context for this event.",
):
    timestamp = server.now() if last_seen is None else last_seen
    raw = {
        "id": event_id,
        "title": title,
        "topic": topic,
        "status": "DEVELOPING" if development else "NEW",
        "last_seen": timestamp,
        "last_change": timestamp,
        "first_seen": timestamp - 3600,
        "significance": significance,
        "velocity": 0.5,
        "novelty": 0.5,
        "corroboration": 0.7,
        "authority": 0.6,
        "urgency": 0.4,
        "source_count": 3,
        "article_count": 3,
        "financial_relevance": financial,
        "geopolitical_relevance": geopolitical,
        "supply_chain_relevance": 0.0,
        "social_relevance": social,
        "entities": server.json.dumps(entities or []),
        "_editorial_development": {
            "score": development,
            "observation_count": 3 if development else 1,
            "spaced_observations": 3 if development else 1,
            "span_seconds": 3600 if development else 0,
            "independent_update_families": 2 if development else 0,
            "what_was_known": "Earlier verified report" if development else "",
            "what_is_new": "A later independent article reports a changed decision" if development else "",
            "when_changed": timestamp if development else None,
            "evidence_article_ids": ["article-a", "article-b"] if development else [],
        },
    }
    obj = {
        "id": event_id,
        "title": title,
        "topic": topic,
        "last_seen": timestamp,
        "india_lens_score": india,
        "india_lens_reasons": ["direct event evidence"] if india else [],
        "signals": {"india_direct": india, "india_material": 0.0, "india_publisher": 0.12 if india else 0.0},
        "world_relevance": world,
        "description": description,
        "article_count": 3,
        "sources": 3,
        "intelligence": {"impact": impact, "confidence": 0.75, "source_strength": 0.7},
    }
    return {"raw": raw, "obj": obj, "impact_score": impact, "important_score": significance}


class EditorialSelectionTests(unittest.TestCase):
    def test_different_lanes_can_reuse_an_event_with_separate_reasons(self):
        item = editorial_item("event-1", "India policy and regional security", topic="Geopolitics", india=0.92, world=0.75, geopolitical=0.9)

        india = server.editorial_select([item], "india", 1)
        world = server.editorial_select([item], "world", 1)

        self.assertEqual(india[0]["id"], world[0]["id"])
        self.assertEqual(india[0]["_editorial_selection"]["lane"], "india")
        self.assertEqual(world[0]["_editorial_selection"]["lane"], "world")
        self.assertNotEqual(india[0]["_editorial_selection"]["reasons"], world[0]["_editorial_selection"]["reasons"])

    def test_developing_requires_separated_update_evidence(self):
        single_batch = editorial_item("single", "A changing policy story", development=0.0)
        sustained = editorial_item("sustained", "A changing security situation", development=0.6)

        selected = server.editorial_select([single_batch, sustained], "developing", 5)

        self.assertEqual([item["id"] for item in selected], ["sustained"])
        self.assertIn("Known:", selected[0]["_editorial_selection"]["reasons"][1])

    def test_related_story_versions_face_diminishing_returns(self):
        first = editorial_item("family-1", "Government approves major energy plan", topic="Energy", entities=["Energy Plan"])
        second = editorial_item("family-2", "Government approves major energy plan update", topic="Energy", entities=["Energy Plan"])
        independent = editorial_item("independent", "Central bank changes interest rate outlook", topic="Economy", significance=0.72, impact=0.72)

        selected = server.editorial_select([first, second, independent], "story_stack", 2)

        selected_ids = [item["id"] for item in selected]
        self.assertTrue({"family-1", "family-2"} & set(selected_ids))
        self.assertIn("independent", [item["id"] for item in selected])
        self.assertFalse({"family-1", "family-2"}.issubset(selected_ids))

    def test_important_score_does_not_decay_with_freshness(self):
        current = editorial_item("current", "A consequential policy decision", last_seen=server.now())
        older = editorial_item("older", "A consequential policy decision", last_seen=server.now() - 48 * 3600)

        self.assertEqual(
            server._editorial_lane_score(current, "important"),
            server._editorial_lane_score(older, "important"),
        )
        self.assertGreater(
            server._editorial_lane_score(current, "story_stack"),
            server._editorial_lane_score(older, "story_stack"),
        )

    def test_world_lane_rejects_local_sports_without_global_consequence(self):
        local_match = editorial_item("match", "A local tennis match ends in straight sets", topic="Sports", world=0.8)
        global_policy = editorial_item("policy", "International energy agreement changes supply", topic="Geopolitics", world=0.8, geopolitical=0.8)

        selected = server.editorial_select([local_match, global_policy], "world", 5)

        self.assertEqual([item["id"] for item in selected], ["policy"])

    def test_repeated_observation_of_one_article_is_not_development(self):
        t = server.now()
        rows = [
            {"article_id": "same", "change_type": "UPDATE", "observed_at": t, "note": "Policy decision announced"},
            {"article_id": "same", "change_type": "UPDATE", "observed_at": t + 3600, "note": "Policy decision announced with new detail"},
        ]
        result = server._editorial_development_evidence(rows, gap_seconds=600)
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["observation_count"], 1)
        self.assertFalse(result["what_is_new"])

    def test_distinct_temporal_evidence_retains_transition(self):
        t = server.now()
        result = server._editorial_development_evidence([
            {"article_id": "a", "change_type": "UPDATE", "observed_at": t, "note": "Court hearing begins · initial arguments"},
            {"article_id": "b", "change_type": "UPDATE", "observed_at": t + 1800, "note": "Court hearing ends · ruling reserved"},
        ], gap_seconds=600)
        self.assertGreater(result["score"], 0)
        self.assertIn("Court hearing begins", result["what_was_known"])
        self.assertIn("Court hearing ends", result["what_is_new"])
        self.assertEqual(len(result["evidence_article_ids"]), 2)

    def test_india_requires_event_relevance_not_publisher_signal(self):
        publisher_only = editorial_item("source-only", "Foreign policy briefing", india=.8)
        publisher_only["obj"]["signals"] = {"india_direct": 0, "india_material": 0, "india_publisher": .8}
        global_india = editorial_item("material", "Oil supply disruption affects Indian imports", india=.72)
        global_india["obj"]["signals"] = {"india_direct": 0, "india_material": .72, "india_publisher": 0}
        self.assertEqual([x["id"] for x in server.editorial_select([publisher_only, global_india], "india", 5)], ["material"])

    def test_impact_rejects_unrelated_sports_tag_noise(self):
        sports = editorial_item("sports", "Local club wins a friendly match", topic="Sports", social=1.0, impact=1.0)
        economy = editorial_item("economy", "Inflation raises household costs", topic="Economy", financial=.8, impact=.8)
        self.assertEqual([x["id"] for x in server.editorial_select([sports, economy], "impact", 5)], ["economy"])

    def test_read_requires_depth(self):
        short = editorial_item("short", "A short breaking headline", description="Short excerpt.")
        deep = editorial_item("deep", "Explainer on policy and economic change", topic="Economy", description=("Detailed background and analysis of the policy, its history, trade-offs, and consequences. " * 4))
        self.assertEqual([x["id"] for x in server.editorial_select([short, deep], "read", 5)], ["deep"])

    def test_latest_payload_is_chronological(self):
        old = editorial_item("old", "Earlier published item", last_seen=server.now() - 3600)
        recent = editorial_item("recent", "Newest published item", last_seen=server.now())
        result = server.build_home_payload([old, recent], [recent, old], [], [], [], [])
        self.assertEqual([x["id"] for x in result["latest"]], ["recent", "old"])

    def test_changed_lane_can_skip_developing_duplicate_if_alternative_exists(self):
        items = [editorial_item(f"dev-{i}", f"Distinct situation {i} reports a new decision", development=.6) for i in range(6)]
        latest = [{"obj": {"id": "fresh", "title": "Fresh article"}}]
        home = server.build_home_payload(items, latest, [], [], [], [])
        developing_ids = {x["id"] for x in home["happening"]}
        changed_ids = {x["id"] for x in home["emerging"]}
        self.assertEqual(len(developing_ids), 5)
        self.assertEqual(len(changed_ids), 1)
        self.assertFalse(developing_ids & changed_ids)


if __name__ == "__main__":
    unittest.main()
