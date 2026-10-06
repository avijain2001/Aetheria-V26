import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class FollowStage6Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "follow-test.sqlite"
        con = sqlite3.connect(self.db_path)
        con.executescript("""
            CREATE TABLE user_follows(session TEXT,event_id TEXT,followed_at REAL,last_seen_change REAL,last_checked REAL,PRIMARY KEY(session,event_id));
            CREATE TABLE schedules(id TEXT PRIMARY KEY,title TEXT,category TEXT,kind TEXT,start_ts REAL,end_ts REAL,time_known INTEGER,url TEXT,description TEXT,importance REAL,updated_at REAL,source_id TEXT);
            CREATE TABLE events(id TEXT PRIMARY KEY,title TEXT,topic TEXT,status TEXT,last_seen REAL,entities TEXT);
            CREATE TABLE event_updates(id INTEGER PRIMARY KEY,event_id TEXT,observed_at REAL,change_type TEXT,note TEXT);
        """)
        now = server.now()
        con.execute("INSERT INTO schedules VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
            "sch_test_policy", "Central bank policy meeting", "Economy", "policy_meeting",
            now + 86400, now + 90000, 0, "https://example.test/calendar", "Policy rate decision meeting", .8, now, "src_test"))
        con.execute("INSERT INTO events VALUES(?,?,?,?,?,?)", (
            "evt_test_unrelated", "Local council policy covers street lighting", "Local", "NEW",
            now, json.dumps(["Local Council"])))
        con.execute("INSERT INTO events VALUES(?,?,?,?,?,?)", (
            "evt_test_generic", "Policy meeting schedule update", "Economy", "NEW",
            now, json.dumps([])))
        con.commit()
        con.close()
        self.patch_db = patch.object(server, "DB_FILE", self.db_path)
        self.patch_db.start()

    def tearDown(self):
        self.patch_db.stop()
        self.temp.cleanup()

    def test_schedule_follow_persists_across_reload_and_connects_related_reporting(self):
        followed = server.toggle_follow("stable-session", "sch_test_policy", "follow")
        self.assertTrue(followed["following"])

        # Simulate a later observed report after the schedule was followed.
        con = server.db()
        con.execute("INSERT INTO events VALUES(?,?,?,?,?,?)", (
            "evt_test_related", "Central bank policy rate changes borrowing costs", "Economy", "DEVELOPING",
            server.now(), json.dumps(["Central Bank"])))
        con.commit()
        con.close()

        after_reload = server.get_follow_up_data("stable-session")
        self.assertIn("sch_test_policy", after_reload["followed_ids"])
        schedule = next(item for item in after_reload["active"] if item["id"] == "sch_test_policy")
        related_ids = {item["id"] for item in schedule["related"]}
        self.assertIn("evt_test_related", related_ids)
        self.assertNotIn("evt_test_unrelated", related_ids)
        self.assertNotIn("evt_test_generic", related_ids)

        con = server.db_read()
        count = con.execute("SELECT COUNT(*) AS n FROM user_follows WHERE session=? AND event_id=?", (
            "stable-session", "sch_test_policy")).fetchone()["n"]
        con.close()
        self.assertEqual(count, 1)

    def test_future_selection_uses_all_supplied_categories_without_static_event_fallback(self):
        now = server.now()
        events = [
            {"id": "schedule-india", "title": "India election commission decision", "category": "Politics", "kind": "scheduled", "start_ts": now + 7200, "importance": .8},
            {"id": "schedule-global", "title": "Global technology standards meeting", "category": "Technology", "kind": "scheduled", "start_ts": now + 172800, "importance": .75},
        ]
        selected = server.select_home_future(events, limit=2, at=now)
        self.assertEqual({item["id"] for item in selected}, {"schedule-india", "schedule-global"})
        self.assertFalse(server.select_home_future([], limit=2, at=now))


if __name__ == "__main__":
    unittest.main()
