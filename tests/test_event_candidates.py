import sqlite3
import unittest

from server import _interleave_event_candidate_paths, _load_event_candidates


class EventCandidateSelectionTests(unittest.TestCase):
    def test_interleave_deduplicates_shared_event_ids_and_respects_bound(self):
        paths = [
            ["recent-1", "recent-2", "shared"],
            ["significant-1", "shared", "significant-2"],
            ["india-1", "india-2", "shared"],
        ]
        selected = _interleave_event_candidate_paths(paths, 6)
        self.assertEqual(selected, ["recent-1", "significant-1", "india-1", "recent-2", "shared", "india-2"])
        self.assertEqual(len(selected), len(set(selected)))

    def test_signal_paths_recover_events_outside_recency_and_stay_bounded(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute("""CREATE TABLE events(
            id TEXT PRIMARY KEY,title TEXT,last_seen REAL,significance REAL,velocity REAL,
            india_relevance REAL,financial_relevance REAL,geopolitical_relevance REAL,
            supply_chain_relevance REAL,social_relevance REAL,corroboration REAL,
            source_count INTEGER,novelty REAL,last_change REAL
        )""")
        rows = [
            ("recent", "Recent ordinary event", 1000, .1, .1, .1, .1, .1, .1, .1, .1, 1, .1, 999),
            ("significant", "Older significant event", 900, .95, .2, .1, .1, .1, .1, .1, .2, 1, .2, 899),
            ("india", "Older India relevant event", 800, .2, .2, .95, .2, .1, .1, .1, .2, 1, .2, 799),
            ("consequence", "Older global consequence event", 700, .2, .2, .1, .95, .1, .1, .1, .2, 1, .2, 699),
            ("corroborated", "Older well corroborated event", 600, .2, .2, .1, .1, .1, .1, .1, .95, 5, .2, 599),
            ("developing", "Older rapidly developing event", 500, .2, .95, .1, .1, .1, .1, .1, .2, 1, .2, 499),
            ("changed", "Older unusually novel event", 400, .2, .2, .1, .1, .1, .1, .1, .2, 1, .95, 399),
        ]
        con.executemany("INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        selected = _load_event_candidates(con, 0, limit=6, path_limit=1)
        selected_ids = [row["id"] for row in selected]
        self.assertLessEqual(len(selected_ids), 6)
        self.assertEqual(len(selected_ids), len(set(selected_ids)))
        self.assertIn("recent", selected_ids)
        self.assertIn("significant", selected_ids)
        self.assertIn("india", selected_ids)
        self.assertIn("consequence", selected_ids)
        con.close()


if __name__ == "__main__":
    unittest.main()
