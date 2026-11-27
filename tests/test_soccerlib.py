#!/usr/bin/env python3

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from soccerlib import merge_schedule, parse_schedule, parse_standings, parse_time_range, refresh_due  # noqa: E402


STANDINGS = """
<table class="table ssr-table"><thead><tr><th>Team</th><th>G</th><th>W</th><th>T</th><th>L</th><th>GF</th><th>GA</th><th>GD</th><th>SO</th><th>PTS</th><th>Last 5</th><th>Links</th></tr></thead>
<tbody><tr><td><span>Turf Kings</span> <span>(Black)</span></td><td>5</td><td>4</td><td>1</td><td>0</td><td>22</td><td>6</td><td>16</td><td>1</td><td>13</td><td> T W W W W </td><td><a title="View Schedule" href="index.php?page=SCHEDULES&amp;division_id=103644&amp;team_id=336925">schedule</a></td></tr></tbody></table>
"""

SCHEDULE = """
<table class="table ssr-table"><thead><tr><th>Home</th><th>Away</th><th></th><th>Location</th><th>Notes</th><th>Type</th></tr></thead><tbody>
<tr class="day_row"><td colspan="6"><strong>Monday, December 21, 2026</strong></td></tr>
<tr><td>Carvetii FC (White)</td><td>Turf Kings (Black)</td><td>11:00-12:00 AM</td><td><a href="https://maps.example/field">DOME 3</a></td><td>027 - Regular Season</td><td>R</td></tr>
</tbody></table>
"""


class ParserTests(unittest.TestCase):
    def test_parses_standings_and_source_ids(self):
        teams = parse_standings(STANDINGS, "https://example.test")
        self.assertEqual(teams[0]["name"], "Turf Kings")
        self.assertEqual(teams[0]["form"], ["T", "W", "W", "W", "W"])
        self.assertEqual(teams[0]["points"], 13)
        self.assertIn("team_id=336925", teams[0]["schedule_url"])

    def test_midnight_end_rolls_to_next_day(self):
        start, end = parse_time_range("Monday, December 21, 2026", "11:00-12:00 AM", "America/Toronto")
        self.assertEqual(start.day, 21)
        self.assertEqual(end.day, 22)
        self.assertEqual((end - start).seconds, 3600)

    def test_parses_schedule(self):
        games = parse_schedule(SCHEDULE, "https://example.test", "America/Toronto")
        self.assertEqual(games[0]["away"], "Turf Kings")
        self.assertEqual(games[0]["location"], "DOME 3")
        self.assertTrue(games[0]["end"].startswith("2026-12-22T00:00"))

    def test_post_game_refresh_window(self):
        config = {"updates": {"post_game_delay_minutes": 5, "result_retry_minutes": 90, "daily_refresh_hours": 24}}
        previous = {
            "generated_at": "2026-12-21T22:00:00Z",
            "team": {"played": 5},
            "schedule": [{"end": "2026-12-21T23:00:00+00:00", "expected_played_after": 6}],
        }
        due, reason = refresh_due(previous, config, datetime(2026, 12, 21, 23, 5, tzinfo=timezone.utc))
        self.assertTrue(due)
        self.assertIn("post-game", reason)

    def test_merge_retains_just_ended_game(self):
        old = {
            "team": {"played": 5},
            "schedule": [{"id": "old", "start": "2026-12-21T21:00:00+00:00", "end": "2026-12-21T22:00:00+00:00", "expected_played_after": 6}],
        }
        current = {"team": {"played": 5}, "schedule": []}
        merge_schedule(old, current, datetime(2026, 12, 21, 22, 5, tzinfo=timezone.utc))
        self.assertEqual(current["schedule"][0]["status"], "ended")


if __name__ == "__main__":
    unittest.main()
