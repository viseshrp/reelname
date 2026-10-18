from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import click
from rapidfuzz import fuzz
from rapidfuzz.utils import default_process

from .constants import (
    CACHE_TTL_HIT,
    CACHE_TTL_MISS,
    MATCH_SCORE_WITH_YEAR,
    MATCH_SCORE_WITHOUT_YEAR,
    TMDB_SEARCH_URL,
)
from .exceptions import TMDbAuthError, TMDbRequestError
from .parsing import ParsedName

# Per kind of search: the year filter parameter, and the result's title and date fields
_FIELDS = {
    "movie": ("year", "title", "release_date"),
    "tv": ("first_air_date_year", "name", "first_air_date"),
}


@dataclass(frozen=True)
class Match:
    """A TMDb title confirmed for a file."""

    title: str
    year: str


def search(kind: str, query: str, year: str | None, api_key: str) -> list[dict[str, Any]]:
    """
    Search TMDb for movies (kind "movie") or TV shows (kind "tv") called `query`,
    released or first aired in `year` when given.

    `api_key` may be a v3 API key or a v4 API read access token (a JWT, starting "eyJ").
    Raises TMDbAuthError if TMDb rejects the key, TMDbRequestError for any other failure.
    """
    year_param = _FIELDS[kind][0]
    params = {"query": query}
    if year:
        params[year_param] = year
    headers = {"Accept": "application/json"}
    if api_key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        params["api_key"] = api_key

    # S310 guards against file:// and custom schemes; the URL here is a fixed https endpoint.
    url = f"{TMDB_SEARCH_URL.format(kind=kind)}?{urlencode(params)}"
    request = Request(url, headers=headers)  # noqa: S310
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310
            payload = json.load(response)
    except HTTPError as exc:
        if exc.code == 401:
            raise TMDbAuthError from exc
        raise TMDbRequestError(str(exc)) from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise TMDbRequestError(str(exc)) from exc

    results: list[dict[str, Any]] = payload.get("results", [])
    return results


def cache_path() -> Path:
    """Where searches are cached: $REELNAME_CACHE_DIR, else the user cache directory."""
    if custom := os.environ.get("REELNAME_CACHE_DIR"):
        return Path(custom) / "tmdb.sqlite3"
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "reelname" / "tmdb.sqlite3"


def _connect() -> sqlite3.Connection:
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.execute(
        "CREATE TABLE IF NOT EXISTS searches"
        " (key TEXT PRIMARY KEY, fetched_at REAL NOT NULL, results TEXT NOT NULL)"
    )
    return db


def _read_cache(key: str) -> list[dict[str, Any]] | None:
    with closing(_connect()) as db:
        row = db.execute(
            "SELECT fetched_at, results FROM searches WHERE key = ?", (key,)
        ).fetchone()
    if row is None:
        return None
    fetched_at, body = row
    results: list[dict[str, Any]] = json.loads(body)
    ttl = CACHE_TTL_HIT if results else CACHE_TTL_MISS
    return results if time.time() - fetched_at < ttl.total_seconds() else None


def _write_cache(key: str, results: list[dict[str, Any]]) -> None:
    with closing(_connect()) as db, db:
        db.execute(
            "INSERT OR REPLACE INTO searches VALUES (?, ?, ?)",
            (key, time.time(), json.dumps(results)),
        )


_cache_warning_shown = False


def _warn_cache_unavailable(exc: Exception) -> None:
    global _cache_warning_shown
    if not _cache_warning_shown:
        click.echo(f"⚠️ TMDb cache unavailable, searching without it: {exc}")
        _cache_warning_shown = True


def cached_search(kind: str, query: str, year: str | None, api_key: str) -> list[dict[str, Any]]:
    """
    `search`, answered from the on-disk cache when it has a fresh result, so re-runs
    and watch mode don't repeat the same searches. Failed searches aren't cached.
    """
    key = json.dumps([kind, query.casefold(), year])
    try:
        cached = _read_cache(key)
    except (OSError, sqlite3.Error) as exc:
        _warn_cache_unavailable(exc)
        return search(kind, query, year, api_key)
    if cached is not None:
        return cached

    results = search(kind, query, year, api_key)
    try:
        _write_cache(key, results)
    except (OSError, sqlite3.Error) as exc:
        _warn_cache_unavailable(exc)
    return results


def get_match_score(title: str, candidate: str) -> float:
    """
    Combine three metrics and take the minimum:
      - fuzz.ratio
      - fuzz.token_sort_ratio
      - fuzz.partial_token_sort_ratio
    This punishes missing tokens, order-changes, and trivial substrings.
    Case and punctuation are ignored, so "THE.DARK.KNIGHT" matches "The Dark Knight".
    """
    return min(
        fuzz.ratio(title, candidate, processor=default_process),
        fuzz.token_sort_ratio(title, candidate, processor=default_process),
        fuzz.partial_token_sort_ratio(title, candidate, processor=default_process),
    )


def find_matches(parsed: ParsedName, api_key: str) -> list[Match]:
    """
    Look the title up on TMDb (TV shows for episodes, movies otherwise):
      - With a year: the best candidate from that year, if it scores well enough.
      - Without a year: every distinct candidate that scores very well. More than one
        means the name is ambiguous, like a remake with the same title.
    An empty list means no match.
    """
    kind = "tv" if parsed.is_episode else "movie"
    _, title_field, date_field = _FIELDS[kind]

    scored: list[tuple[float, Match]] = []
    for result in cached_search(kind, parsed.title, parsed.year, api_key):
        candidate = result.get(title_field)
        candidate_year = (result.get(date_field) or "")[:4]
        if not candidate or not candidate_year or (parsed.year and candidate_year != parsed.year):
            continue
        scored.append((get_match_score(parsed.title, candidate), Match(candidate, candidate_year)))

    if parsed.year:
        best = max(scored, key=lambda item: item[0], default=None)
        return [best[1]] if best and best[0] >= MATCH_SCORE_WITH_YEAR else []
    return list(dict.fromkeys(m for score, m in scored if score >= MATCH_SCORE_WITHOUT_YEAR))
