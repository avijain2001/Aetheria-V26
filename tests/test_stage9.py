import pathlib
import sqlite3
import unittest

import server


ROOT = pathlib.Path(__file__).resolve().parents[1]


class Stage9EvidenceTests(unittest.TestCase):
    def test_old_velocity_expires_with_its_six_hour_evidence_window(self):
        recent = {"velocity": 0.8, "last_seen": 1000, "last_change": 1000}
        self.assertAlmostEqual(server._effective_event_velocity(recent, at=1000), 0.8)
        self.assertAlmostEqual(server._effective_event_velocity(recent, at=1000 + 3 * 3600), 0.4)
        self.assertEqual(server._effective_event_velocity(recent, at=1000 + 6 * 3600), 0.0)

    def test_time_current_significance_uses_decayed_activity(self):
        event = {
            "velocity": 1.0, "last_change": 1000, "first_seen": 1000,
            "corroboration": 0.0, "authority": 0.0, "urgency": 0.0,
            "india_relevance": 0.0,
        }
        fresh = server._current_event_significance(event, at=1000)
        stale = server._current_event_significance(event, at=1000 + 72 * 3600)
        self.assertGreater(fresh, stale)
        self.assertAlmostEqual(stale, 0.005)

    def test_changed_lane_marks_reporting_without_action_as_low_confidence(self):
        start = 100_000
        result = server._editorial_development_evidence([
            {"article_id": "a", "change_type": "UPDATE", "observed_at": start, "note": "Council reviews a transport plan"},
            {"article_id": "b", "change_type": "UPDATE", "observed_at": start + 1800, "note": "Council discusses the transport plan"},
        ], gap_seconds=600)
        self.assertEqual(result["confidence"], "LOW")
        self.assertEqual(result["kind"], "new_reporting")

    def test_changed_lane_detects_explicit_new_action(self):
        start = 100_000
        result = server._editorial_development_evidence([
            {"article_id": "a", "change_type": "UPDATE", "observed_at": start, "note": "Council reviews a transport plan"},
            {"article_id": "b", "change_type": "UPDATE", "observed_at": start + 1800, "note": "Council approves the transport plan"},
        ], gap_seconds=600)
        self.assertEqual(result["confidence"], "MEDIUM")
        self.assertEqual(result["kind"], "likely_real_world_change")

    def test_world_lane_identifies_weather_graphics_without_impact(self):
        self.assertTrue(server._world_weather_format_only({
            "title": "Hurricane Rachel Graphics",
            "topic": "Weather",
            "description": "Wind Speed Probabilities last updated at 09:28 GMT",
        }))
        self.assertFalse(server._world_weather_format_only({
            "title": "Hurricane makes landfall; coastal evacuations ordered",
            "topic": "Weather",
            "description": "Residents have been moved from affected areas.",
        }))

    def test_candidate_pool_remains_bounded_and_uses_current_velocity(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute("""CREATE TABLE events(
            id TEXT PRIMARY KEY,title TEXT,last_seen REAL,significance REAL,velocity REAL,
            india_relevance REAL,financial_relevance REAL,geopolitical_relevance REAL,
            supply_chain_relevance REAL,social_relevance REAL,corroboration REAL,
            source_count INTEGER,novelty REAL,last_change REAL
        )""")
        con.executemany("INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            ("recent", "Recent ordinary event", 1000, .1, .1, .1, .1, .1, .1, .1, .1, 1, .1, 1000),
            ("stale-velocity", "Old activity event", 900, .2, 1.0, .1, .1, .1, .1, .1, .1, 1, .1, 100),
        ])
        selected = server._load_event_candidates(con, 0, limit=2, path_limit=1, at=1000)
        self.assertLessEqual(len(selected), 2)
        self.assertEqual(len({row["id"] for row in selected}), len(selected))
        con.close()


class Stage9UiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    def test_navigation_resets_scroll_before_waiting_for_route_data(self):
        start = self.js.index("async function navigate(route, options={})")
        end = self.js.index("\n  function bindHome()", start)
        nav = self.js[start:end]
        self.assertIn("const changedView = state.route !== route", nav)
        self.assertIn("await renderRoute()", nav)
        self.assertIn("if (changedView) resetRouteScroll()", nav)
        self.assertLess(nav.index("resetRouteScroll()"), nav.index("await renderRoute()"))
        self.assertIn("function resetRouteScroll()", self.js)
        self.assertIn("window.scrollTo(0,0)", self.js)
        self.assertIn("history.pushState", nav)

    def test_modal_focus_trap_remains_and_modal_open_does_not_use_route_reset(self):
        self.assertIn("if(storyModalOpen() && e.key==='Tab')", self.js)
        self.assertIn("first.focus()", self.js)
        self.assertIn("last.focus()", self.js)
        self.assertIn("function openStory", self.js)

    def test_change_label_does_not_claim_verification_above_evidence(self):
        self.assertIn("const changeLabel=change.confidence==='HIGH'?'STRONG CHANGE EVIDENCE':'LIKELY CHANGE'", self.js)
        self.assertNotIn('class="changed-label">VERIFIED CHANGE</div>', self.js)

    def test_market_movement_uses_dynamic_positive_negative_and_neutral_states(self):
        self.assertIn("Number.isFinite(changeNum) ? changeNum : Number.isFinite(pct) ? pct : null", self.js)
        self.assertIn("movement > 0 ? 'up' : movement < 0 ? 'down' : 'flat'", self.js)
        self.assertIn("cls === 'up' ? '▲' : '='", self.js)
        self.assertIn('class="market-change ${cls}" role="img" aria-label=', self.js)
        self.assertIn("aria-label=\"${esc(direction)}", self.js)
        self.assertIn(".market-change.up { color: var(--market-up); }", self.css)
        self.assertIn(".market-change.down { color: var(--market-down); }", self.css)
        self.assertIn(".market-change.flat { color: var(--market-neutral); }", self.css)
        self.assertIn("--market-neutral: #64748b", self.css)


if __name__ == "__main__":
    unittest.main()
