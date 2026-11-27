"""Fetch and parse the public PowerUp Sports standings and schedule pages."""

from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener
from zoneinfo import ZoneInfo


USER_AGENT = "Mozilla/5.0 (compatible; matchday-dashboard/1.0; +https://github.com/)"


def clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def normal_name(value: str) -> str:
    return clean_text(value).casefold()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class Cell:
    text_parts: list[str] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)
    links: list[dict[str, str]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return clean_text("".join(self.text_parts))


@dataclass
class Row:
    cells: list[Cell] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)


class SSRTableParser(HTMLParser):
    """Small, tolerant parser for the public report tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[Row]] = []
        self._active = False
        self._table_depth = 0
        self._rows: list[Row] = []
        self._row: Row | None = None
        self._cell: Cell | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        if tag == "table":
            if self._active:
                self._table_depth += 1
            elif "ssr-table" in attr.get("class", "").split():
                self._active = True
                self._table_depth = 1
                self._rows = []
            return
        if not self._active:
            return
        if tag == "tr":
            self._row = Row(attrs=attr)
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = Cell(attrs=attr)
        elif tag == "a" and self._cell is not None:
            self._cell.links.append(attr)
        elif tag == "br" and self._cell is not None:
            self._cell.text_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if not self._active:
            return
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.cells.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self._rows.append(self._row)
            self._row = None
        elif tag == "table":
            self._table_depth -= 1
            if self._table_depth == 0:
                self.tables.append(self._rows)
                self._rows = []
                self._active = False

    def handle_data(self, data: str) -> None:
        if self._active and self._cell is not None:
            self._cell.text_parts.append(data)


class SelectParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.selects: dict[str, list[tuple[str, str]]] = {}
        self._select: str | None = None
        self._value: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        if tag == "select":
            self._select = attr.get("id") or attr.get("name")
            if self._select:
                self.selects.setdefault(self._select, [])
        elif tag == "option" and self._select:
            self._value = attr.get("value", "")
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "option" and self._select is not None and self._value is not None:
            self.selects[self._select].append((self._value, clean_text("".join(self._text))))
            self._value = None
            self._text = []
        elif tag == "select":
            self._select = None

    def handle_data(self, data: str) -> None:
        if self._value is not None:
            self._text.append(data)


def select_named(options: list[tuple[str, str]], wanted: str, label: str) -> str:
    wanted_key = normal_name(wanted)
    for value, name in options:
        if value and normal_name(name) == wanted_key:
            return value
    available = ", ".join(name for value, name in options if value) or "none"
    raise ValueError(f"Could not find {label} {wanted!r}. Available: {available}")


def _team_and_colour(value: str) -> tuple[str, str]:
    match = re.match(r"^(.*?)\s*\((.*?)\)\s*$", clean_text(value))
    if match:
        return match.group(1).strip(), match.group(2).strip(" /-")
    return clean_text(value), ""


def _as_int(value: str) -> int:
    return int(clean_text(value).replace("−", "-"))


def parse_standings(html: str, base_url: str) -> list[dict[str, Any]]:
    parser = SSRTableParser()
    parser.feed(html)
    if not parser.tables:
        raise ValueError("No standings table was found in the source response")

    rows = parser.tables[0]
    teams: list[dict[str, Any]] = []
    for row in rows:
        if len(row.cells) < 10 or normal_name(row.cells[0].text) == "team":
            continue
        name, colour = _team_and_colour(row.cells[0].text)
        if not name:
            continue
        links = [link for cell in row.cells for link in cell.links]
        schedule_url = ""
        results_url = ""
        for link in links:
            title = normal_name(link.get("title", ""))
            href = urljoin(base_url + "/", link.get("href", ""))
            if "schedule" in title:
                schedule_url = href
            elif "result" in title:
                results_url = href
        teams.append(
            {
                "rank": len(teams) + 1,
                "name": name,
                "colour": colour,
                "played": _as_int(row.cells[1].text),
                "wins": _as_int(row.cells[2].text),
                "ties": _as_int(row.cells[3].text),
                "losses": _as_int(row.cells[4].text),
                "goals_for": _as_int(row.cells[5].text),
                "goals_against": _as_int(row.cells[6].text),
                "goal_difference": _as_int(row.cells[7].text),
                "shutouts": _as_int(row.cells[8].text),
                "points": _as_int(row.cells[9].text),
                "form": row.cells[10].text.split() if len(row.cells) > 10 else [],
                "schedule_url": schedule_url,
                "results_url": results_url,
            }
        )
    if not teams:
        raise ValueError("The standings table contained no team rows")
    return teams


def parse_time_range(date_label: str, time_label: str, timezone_name: str) -> tuple[datetime, datetime]:
    day = datetime.strptime(clean_text(date_label), "%A, %B %d, %Y").date()
    match = re.match(
        r"^(\d{1,2}:\d{2})(?:\s*([AP]M))?\s*[-–]\s*(\d{1,2}:\d{2})\s*([AP]M)$",
        clean_text(time_label).upper(),
    )
    if not match:
        raise ValueError(f"Unrecognized game time: {date_label} {time_label}")
    start_clock, start_meridiem, end_clock, end_meridiem = match.groups()
    zone = ZoneInfo(timezone_name)
    end = datetime.combine(day, datetime.strptime(f"{end_clock} {end_meridiem}", "%I:%M %p").time(), zone)
    candidates = [start_meridiem] if start_meridiem else ["AM", "PM"]
    ranges: list[tuple[timedelta, datetime, datetime]] = []
    for meridiem in candidates:
        start = datetime.combine(day, datetime.strptime(f"{start_clock} {meridiem}", "%I:%M %p").time(), zone)
        candidate_end = end
        if candidate_end <= start:
            candidate_end += timedelta(days=1)
        ranges.append((candidate_end - start, start, candidate_end))
    _, start, end = min(ranges, key=lambda item: item[0])
    return start, end


def parse_schedule(html: str, base_url: str, timezone_name: str) -> list[dict[str, Any]]:
    parser = SSRTableParser()
    parser.feed(html)
    if not parser.tables:
        raise ValueError("No schedule table was found in the source response")
    rows = parser.tables[0]
    games: list[dict[str, Any]] = []
    date_label = ""
    for row in rows:
        row_class = row.attrs.get("class", "").split()
        if "day_row" in row_class and row.cells:
            date_label = row.cells[0].text
            continue
        if len(row.cells) < 6 or normal_name(row.cells[0].text) == "home":
            continue
        if not date_label:
            raise ValueError("A schedule game appeared without a date heading")
        home, home_colour = _team_and_colour(row.cells[0].text)
        away, away_colour = _team_and_colour(row.cells[1].text)
        start, end = parse_time_range(date_label, row.cells[2].text, timezone_name)
        map_url = ""
        if row.cells[3].links:
            map_url = urljoin(base_url + "/", row.cells[3].links[0].get("href", ""))
        games.append(
            {
                "id": f"{start.isoformat()}|{home}|{away}",
                "date_label": date_label,
                "time_label": row.cells[2].text,
                "start": start.isoformat(timespec="minutes"),
                "end": end.isoformat(timespec="minutes"),
                "home": home,
                "home_colour": home_colour,
                "away": away,
                "away_colour": away_colour,
                "location": row.cells[3].text,
                "map_url": map_url,
                "notes": row.cells[4].text,
                "type": row.cells[5].text,
            }
        )
    return games


def extract_last_modified(html: str) -> str:
    text = clean_text(re.sub(r"<[^>]+>", " ", unescape(html)))
    match = re.search(r"Last Modified:\s*([A-Z][a-z]+ \d{1,2}, \d{4} \d{1,2}:\d{2} [AP]M)", text)
    return match.group(1) if match else ""


class PowerUpClient:
    def __init__(self, base_url: str, request_delay_seconds: float = 0.4) -> None:
        self.base_url = base_url.rstrip("/")
        self.delay = request_delay_seconds
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))
        self._last_request = 0.0

    def get(self, path: str, params: dict[str, Any]) -> tuple[str, str]:
        elapsed = time.monotonic() - self._last_request
        if self._last_request and elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        url = urljoin(self.base_url + "/", path)
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urlencode(params)}"
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xml;q=0.9,*/*;q=0.8"})
        with self.opener.open(request, timeout=30) as response:
            payload = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            final_url = response.geturl()
        self._last_request = time.monotonic()
        return payload.decode(charset, errors="replace"), final_url

    def fetch(self, config: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
        now = now or utc_now()
        source = config["source"]
        season_id = str(source["season_id"])

        season_html, _ = self.get("index.php", {"page": "STANDINGS", "sid": season_id})
        select_parser = SelectParser()
        select_parser.feed(season_html)
        category_id = select_named(select_parser.selects.get("get_gameset_id", []), source["category"], "category")

        gamesets_xml, _ = self.get(
            "reg/getViaAjax.php",
            {
                "category_id": category_id,
                "season_id": season_id,
                "page": "STANDINGS",
                "action": "gamesets_by_category",
            },
        )
        root = ET.fromstring(gamesets_xml)
        gamesets = [
            (node.findtext("gameset_id", ""), node.findtext("gameset_name", ""))
            for node in root.findall("gameset")
        ]
        gameset_id = select_named(gamesets, source["division"], "division")

        standings_html, standings_url = self.get(
            "index.php",
            {
                "page": "STANDINGS",
                "p": 1,
                "sid": season_id,
                "category_id": category_id,
                "gameset_id": gameset_id,
            },
        )
        standings = parse_standings(standings_html, self.base_url)
        target = next((team for team in standings if normal_name(team["name"]) == normal_name(source["team"])), None)
        if target is None:
            available = ", ".join(team["name"] for team in standings)
            raise ValueError(f"Could not find team {source['team']!r}. Available: {available}")
        if not target["schedule_url"]:
            raise ValueError(f"No schedule link was found for {source['team']}")

        schedule_query = parse_qs(urlparse(target["schedule_url"]).query)
        schedule_params = {key: values[0] for key, values in schedule_query.items()}
        schedule_params["p"] = 1
        schedule_html, schedule_url = self.get("index.php", schedule_params)
        schedule = parse_schedule(schedule_html, self.base_url, config["timezone"])

        # Internal source links are useful to the updater, not the generated site data.
        public_standings = []
        for team in standings:
            public_standings.append({key: value for key, value in team.items() if not key.endswith("_url")})

        return {
            "schema_version": 1,
            "generated_at": iso_z(now),
            "source_modified_at": extract_last_modified(schedule_html),
            "league": {
                "season_id": int(season_id) if season_id.isdigit() else season_id,
                "category": source["category"],
                "division": source["division"],
            },
            "team": {key: value for key, value in target.items() if not key.endswith("_url")},
            "standings": public_standings,
            "schedule": schedule,
            "source_urls": {"standings": standings_url, "schedule": schedule_url},
        }


def game_due(game: dict[str, Any], played: int, now: datetime, config: dict[str, Any]) -> bool:
    updates = config["updates"]
    end = parse_iso(game["end"])
    ready = end + timedelta(minutes=updates["post_game_delay_minutes"])
    expires = end + timedelta(minutes=updates["result_retry_minutes"])
    expected = int(game.get("expected_played_after", played + 1))
    return ready <= now <= expires and played < expected


def refresh_due(previous: dict[str, Any] | None, config: dict[str, Any], now: datetime) -> tuple[bool, str]:
    if previous is None:
        return True, "initial fetch"
    played = int(previous["team"]["played"])
    if any(game_due(game, played, now, config) for game in previous.get("schedule", [])):
        return True, "post-game result window"
    age = now - parse_iso(previous["generated_at"])
    if age >= timedelta(hours=config["updates"]["daily_refresh_hours"]):
        return True, "daily schedule refresh"
    return False, "no game update is due"


def merge_schedule(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    now: datetime,
) -> None:
    """Keep recently-ended games so result retry windows survive source removal."""
    played = int(current["team"]["played"])
    upcoming = sorted(current.get("schedule", []), key=lambda game: game["start"])
    for offset, game in enumerate(upcoming, start=1):
        game["expected_played_after"] = played + offset
        game["status"] = "upcoming" if parse_iso(game["end"]) > now else "ended"

    by_id = {game["id"]: game for game in upcoming}
    if previous:
        for old in previous.get("schedule", []):
            if old["id"] in by_id:
                # Preserve the original expectation across ordinary refreshes.
                by_id[old["id"]]["expected_played_after"] = old.get(
                    "expected_played_after", by_id[old["id"]]["expected_played_after"]
                )
                continue
            end = parse_iso(old["end"])
            if now - end <= timedelta(hours=6):
                retained = dict(old)
                retained["status"] = "processed" if played >= int(old.get("expected_played_after", played + 1)) else "ended"
                by_id[old["id"]] = retained
    current["schedule"] = sorted(by_id.values(), key=lambda game: game["start"])


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
