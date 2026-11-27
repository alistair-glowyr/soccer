#!/usr/bin/env python3
"""Render the static dashboard from data/latest.json."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_signed(value: int) -> str:
    return f"+{value}" if value > 0 else str(value)


def ordinal(value: int) -> str:
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def icon(name: str) -> str:
    icons = {
        "calendar": '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M7 2v3M17 2v3M3.5 9h17M5 4h14a2 2 0 0 1 2 2v14H3V6a2 2 0 0 1 2-2Z"/></svg>',
        "clock": '<svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
        "pin": '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/></svg>',
    }
    return icons[name]


def main() -> int:
    config = load(ROOT / "config.json")
    data = load(ROOT / "data" / "latest.json")
    team = data["team"]
    team_name = team["name"]
    now = datetime.now(ZoneInfo(config["timezone"]))
    upcoming = [game for game in data["schedule"] if dt(game["end"]) > now]
    upcoming.sort(key=lambda game: game["start"])
    next_game = upcoming[0] if upcoming else None

    if next_game:
        start = dt(next_game["start"])
        opponent = next_game["away"] if next_game["home"] == team_name else next_game["home"]
        side = "Home" if next_game["home"] == team_name else "Away"
        hero_match = f"""
          <div class="next-kicker"><span></span>Next match</div>
          <div class="next-grid">
            <div class="date-tile"><strong>{escape(start.strftime('%d'))}</strong><span>{escape(start.strftime('%b').upper())}</span></div>
            <div class="next-copy">
              <p class="versus">{escape(side)} · vs</p>
              <h2>{escape(opponent)}</h2>
              <div class="match-meta">
                <span>{icon('calendar')}{escape(start.strftime('%A, %B %-d'))}</span>
                <span>{icon('clock')}{escape(start.strftime('%-I:%M %p'))}</span>
                <a href="{escape(next_game['map_url'])}" target="_blank" rel="noopener">{icon('pin')}{escape(next_game['location'])}</a>
              </div>
            </div>
          </div>"""
    else:
        hero_match = """
          <div class="next-kicker"><span></span>Schedule</div>
          <div class="season-complete"><h2>No upcoming match listed</h2><p>We’ll pick up the next fixture when the club posts it.</p></div>"""

    schedule_cards = []
    for index, game in enumerate(upcoming):
        start = dt(game["start"])
        is_home = game["home"] == team_name
        opponent = game["away"] if is_home else game["home"]
        schedule_cards.append(
            f"""
            <article class="fixture{' is-next' if index == 0 else ''}">
              <div class="fixture-date"><span>{escape(start.strftime('%a'))}</span><strong>{escape(start.strftime('%d'))}</strong><small>{escape(start.strftime('%b'))}</small></div>
              <div class="fixture-body">
                <div class="fixture-label"><span class="pill">{'Home' if is_home else 'Away'}</span>{'Next up' if index == 0 else escape(game['notes'].replace(' - Regular Season', ''))}</div>
                <h3><span>vs</span> {escape(opponent)}</h3>
                <div class="fixture-meta">
                  <span>{icon('clock')}{escape(start.strftime('%-I:%M %p'))}</span>
                  <a href="{escape(game['map_url'])}" target="_blank" rel="noopener">{icon('pin')}{escape(game['location'])}</a>
                </div>
              </div>
            </article>"""
        )
    if not schedule_cards:
        schedule_cards.append('<div class="empty-state"><p>No upcoming fixtures are currently listed.</p></div>')

    rows = []
    for row in data["standings"]:
        target = row["name"] == team_name
        form = "".join(f'<span class="form form-{escape(value.lower())}">{escape(value)}</span>' for value in row["form"])
        rows.append(
            f"""
            <tr{' class="is-team"' if target else ''}>
              <td class="rank">{row['rank']}</td>
              <th scope="row"><span class="team-cell">{escape(row['name'])}{'<em>You</em>' if target else ''}</span></th>
              <td>{row['played']}</td><td class="wide">{row['wins']}</td><td class="wide">{row['ties']}</td><td class="wide">{row['losses']}</td>
              <td class="wide">{row['goals_for']}</td><td class="wide">{row['goals_against']}</td><td>{fmt_signed(row['goal_difference'])}</td>
              <td class="form-cell wide">{form}</td><td class="points">{row['points']}</td>
            </tr>"""
        )

    updated = dt(data["generated_at"]).astimezone(ZoneInfo(config["timezone"]))
    source_url = data["source_urls"]["standings"]
    division_short = data["league"]["division"].replace(" Regular Season", "")
    record = f"{team['wins']}–{team['ties']}–{team['losses']}"

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#09231d">
  <meta name="description" content="A fast, mobile-friendly view of the {escape(team_name)} schedule and standings.">
  <title>{escape(team_name)} · Matchday</title>
  <link rel="icon" href="favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="styles.css">
  <script src="app.js" defer></script>
</head>
<body>
  <header class="hero">
    <div class="topbar wrap">
      <a class="brand" href="#top" aria-label="{escape(team_name)} home"><span class="mark">TK</span><span><strong>{escape(team_name)}</strong><small>Matchday</small></span></a>
      <span class="league">{escape(data['league']['category'])} · {escape(division_short)}</span>
    </div>
    <div class="hero-grid wrap" id="top">
      <div class="identity">
        <p class="eyebrow">Burlington Soccer Club</p>
        <h1>Everything you need.<br><span>Nothing to click through.</span></h1>
        <div class="quick-stats" aria-label="Team summary">
          <div><strong>{ordinal(team['rank'])}</strong><span>Position</span></div>
          <div><strong>{record}</strong><span>W–T–L</span></div>
          <div><strong>{team['points']}</strong><span>Points</span></div>
          <div><strong>{fmt_signed(team['goal_difference'])}</strong><span>Goal diff</span></div>
        </div>
      </div>
      <section class="next-card" aria-label="Next match">{hero_match}</section>
    </div>
  </header>

  <main class="wrap main-content">
    <nav class="tabs" aria-label="Dashboard sections">
      <button class="tab is-active" type="button" data-tab="schedule" aria-selected="true" aria-controls="schedule">Schedule <span>{len(upcoming)}</span></button>
      <button class="tab" type="button" data-tab="standings" aria-selected="false" aria-controls="standings">Standings <span>{team['rank']}/{len(data['standings'])}</span></button>
    </nav>

    <section class="panel is-active" id="schedule" aria-labelledby="schedule-title">
      <div class="section-heading"><div><p class="eyebrow dark">Coming up</p><h2 id="schedule-title">Fixture list</h2></div><p>Times shown in Toronto time</p></div>
      <div class="fixtures">{''.join(schedule_cards)}</div>
    </section>

    <section class="panel" id="standings" aria-labelledby="standings-title" hidden>
      <div class="section-heading"><div><p class="eyebrow dark">League table</p><h2 id="standings-title">{escape(division_short)}</h2></div><p>{team['played']} matches played</p></div>
      <div class="table-shell">
        <table>
          <thead><tr><th>#</th><th>Team</th><th title="Played">P</th><th class="wide" title="Wins">W</th><th class="wide" title="Ties">T</th><th class="wide" title="Losses">L</th><th class="wide" title="Goals for">GF</th><th class="wide" title="Goals against">GA</th><th title="Goal difference">GD</th><th class="wide">Form</th><th>Pts</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
      <p class="mobile-note">Showing the essential columns. Rotate your phone or use a wider screen for the full table.</p>
    </section>
  </main>

  <footer>
    <div class="wrap footer-inner">
      <div><span class="pulse"></span><p><strong>Last synced <time datetime="{escape(data['generated_at'])}">{escape(updated.strftime('%b %-d at %-I:%M %p'))}</time></strong><br><span>{escape(data.get('source_modified_at') or 'Source timestamp unavailable')}</span></p></div>
      <p>An unofficial dashboard · <a href="{escape(source_url)}" target="_blank" rel="noopener">View the club source</a></p>
    </div>
  </footer>
</body>
</html>
"""

    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "index.html").write_text(html, encoding="utf-8")
    for name in ("styles.css", "app.js", "favicon.svg"):
        shutil.copyfile(ROOT / "site" / name, docs / name)
    (docs / ".nojekyll").touch()
    print(f"Built {docs / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
