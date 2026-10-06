import json
import pathlib
import unittest
from unittest.mock import patch

import server


ROOT = pathlib.Path(__file__).resolve().parents[1]


class Stage10SearchTests(unittest.TestCase):
    def test_exact_company_question_beats_newer_unrelated_finance_match(self):
        query = "Is this IT solutions stock’s 34.10% run since July just getting started?"
        exact = server._search_relevance_score(
            query,
            "Is this IT solutions stock’s 34.10% run since July just getting started?",
            published=1_000,
            at=1_000,
        )
        unrelated = server._search_relevance_score(
            query,
            "India forex reserves fall as global markets rally",
            "Investors look at market conditions",
            topic="Markets",
            published=1_000,
            at=1_000,
        )
        self.assertGreater(exact, unrelated)

    def test_title_entity_match_outweighs_description_only_overlap(self):
        query = "Acme earnings guidance"
        title_match = server._search_relevance_score(query, "Acme earnings guidance raised")
        description_match = server._search_relevance_score(
            query, "Company updates outlook", "Acme earnings guidance was announced"
        )
        self.assertGreater(title_match, description_match)

    def test_exact_numeric_phrase_outweighs_event_context_overlap(self):
        query = "IT Solutions 34.10% since July"
        direct = server._search_relevance_score(query, "IT Solutions gains 34.10% since July")
        contextual = server._search_relevance_score(
            query, "Forex reserves decline", entity_context="IT Solutions stock discussion"
        )
        self.assertGreater(direct, contextual)


class Stage10VerificationTests(unittest.TestCase):
    def test_one_publisher_is_reported_and_two_independent_publishers_are_corroborated(self):
        self.assertEqual(server._verification_state(1, 0), "REPORTED")
        self.assertEqual(server._verification_state(2, 0), "CORROBORATED")

    def test_confirmation_requires_configured_official_evidence_by_default(self):
        self.assertTrue(server.CONFIRMATION_REQUIRE_OFFICIAL)
        self.assertEqual(server._verification_state(2, 0), "CORROBORATED")
        self.assertEqual(server._verification_state(2, 1), "CONFIRMED")

    def test_conflicting_claims_override_confirmation(self):
        self.assertEqual(server._verification_state(4, 1, conflicts=1), "DISPUTED")

    def test_discovery_sources_do_not_count_as_credible_independent_publishers(self):
        t = 100_000
        rows = [
            {"id": "a", "title": "Council announces emergency transport changes", "domain": "publisher.example", "tier": "publisher"},
            {"id": "b", "title": "Council announces emergency transport changes", "domain": "discovery.example", "tier": "discovery"},
        ]
        metrics = server._event_evidence_metrics(rows, [], t, t - 600)
        self.assertEqual(metrics["independent_sources"], 1)
        self.assertEqual(metrics["credible_independent_sources"], 1)

    def test_syndicated_copies_contribute_one_credible_source(self):
        title = "Central bank announces new policy framework for lending"
        rows = [
            {"id": "a", "title": title, "domain": "publisher-one.example", "tier": "publisher"},
            {"id": "b", "title": title, "domain": "publisher-two.example", "tier": "publisher"},
            {"id": "c", "title": title, "domain": "publisher-three.example", "tier": "publisher"},
        ]
        metrics = server._event_evidence_metrics(rows, [], 100_000, 99_000)
        self.assertEqual(metrics["credible_independent_sources"], 1)
        self.assertEqual(server._verification_state(metrics["credible_independent_sources"]), "REPORTED")


class Stage10StartupAndUiTests(unittest.TestCase):
    def test_local_browser_opens_only_after_local_version_endpoint_answers(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _size):
                return json.dumps({"ok": True, "version": server.VERSION}).encode()

        with patch.object(server.urllib.request, "urlopen", return_value=Response()) as request:
            with patch.object(server.webbrowser, "open_new_tab", return_value=True) as opener:
                self.assertTrue(server._open_local_browser_when_ready("http://127.0.0.1:8000", timeout=1))
        request.assert_called_once_with("http://127.0.0.1:8000/api/version", timeout=1.5)
        opener.assert_called_once_with("http://127.0.0.1:8000")

    def test_navigation_resets_before_await_and_keeps_back_forward_routes(self):
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        nav = app.split("async function navigate(route, options={})", 1)[1].split("function bindHome", 1)[0]
        self.assertLess(nav.index("resetRouteScroll()"), nav.index("await renderRoute()"))
        self.assertIn("history.pushState", nav)
        self.assertIn("navigate(r,{history:false})", app)

    def test_search_shows_skeleton_and_does_not_call_matches_verified(self):
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function loadingRows", app)
        self.assertIn("Searching live reporting...", app)
        self.assertNotIn("Searching verified reporting", app)
        self.assertIn("input.focus({preventScroll:true})", app)

    def test_route_skeleton_respects_reduced_motion(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn(".route-skeleton-row", html)
        self.assertIn("prefers-reduced-motion:reduce", html)

    def test_event_confirmation_is_recomputed_from_current_evidence(self):
        code = (ROOT / "server.py").read_text(encoding="utf-8")
        self.assertNotIn('if e["status"]=="CONFIRMED"', code)
        self.assertIn("conflicts=_conflict_pairs(evidence_rows)", code)


if __name__ == "__main__":
    unittest.main()
