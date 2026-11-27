#!/usr/bin/env python3
"""Refresh the committed snapshot when a game result or daily sync is due."""

from __future__ import annotations

import argparse
from pathlib import Path

from soccerlib import PowerUpClient, load_json, merge_schedule, refresh_due, save_json, utc_now


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--if-due", action="store_true", help="Skip the source request unless an update is due")
    mode.add_argument("--force", action="store_true", help="Refresh regardless of the schedule")
    args = parser.parse_args()

    config = load_json(ROOT / "config.json")
    data_path = ROOT / "data" / "latest.json"
    previous = load_json(data_path) if data_path.exists() else None
    now = utc_now()
    due, reason = refresh_due(previous, config, now)
    if args.if_due and not due:
        print(f"Skipping source request: {reason}.")
        return 0

    print(f"Refreshing soccer data: {'manual refresh' if args.force else reason}.")
    client = PowerUpClient(
        config["source"]["base_url"],
        request_delay_seconds=float(config["updates"].get("request_delay_seconds", 0.4)),
    )
    current = client.fetch(config, now=now)
    merge_schedule(previous, current, now)
    save_json(data_path, current)
    print(
        f"Saved {len(current['standings'])} teams and "
        f"{sum(game['status'] == 'upcoming' for game in current['schedule'])} upcoming games."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
