# Turf Kings Matchday

A self-updating, mobile-friendly view of the Turf Kings schedule and MOA North
standings. It reads Burlington Soccer Club's public PowerUp Sports pages, builds a
static dashboard, and deploys it to GitHub Pages.

## What it does

- Resolves the configured category and division names to PowerUp's changing IDs.
- Shows the next match, all posted upcoming fixtures, and a responsive league table.
- Checks every five minutes, but only contacts the club site after a scheduled game
  or when the daily schedule refresh is due.
- Retries during the configured post-game window until the team's games-played count
  changes, then stops polling.
- Uses only the Python standard library at runtime.

## Configuration

Edit [`config.json`](config.json):

| Setting | Meaning |
|---|---|
| `source.season_id` | The `sid` number in the PowerUp standings URL. |
| `source.category` | Category label exactly as PowerUp displays it. |
| `source.division` | Standings division label exactly as displayed. |
| `source.team` | Team name exactly as displayed. |
| `updates.post_game_delay_minutes` | Wait after the scheduled end before checking. |
| `updates.result_retry_minutes` | Keep checking for a late-posted result. |
| `updates.daily_refresh_hours` | Background refresh interval for fixture changes. |

When a new league begins, those four `source` values are the only expected changes.
The updater reports the available labels when a configured name no longer matches.

## Run locally

```bash
python3 tests/test_soccerlib.py
python3 scripts/update_data.py --force
python3 scripts/build_site.py
python3 -m http.server 8000 --directory docs
```

Then open <http://localhost:8000>.

## GitHub Pages

The workflow in [`.github/workflows/update.yml`](.github/workflows/update.yml) deploys
on every push, on manual runs, and when a scheduled refresh produces new data. Pages
must use **GitHub Actions** as its build source.

This is an unofficial dashboard. The source site remains the authority for schedule
and standings information.
