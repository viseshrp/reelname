from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import click
from rapidfuzz import fuzz
from rapidfuzz.utils import default_process

from .constants import (
    ALTERNATIVE_TITLE_CANDIDATES,
    CACHE_TTL_HIT,
    CACHE_TTL_MISS,
    MATCH_SCORE_WITH_YEAR,
    MATCH_SCORE_WITHOUT_YEAR,
    TMDB_API_URL,
    TMDB_ATTEMPTS,
    TMDB_MAX_RETRY_DELAY,
    TMDB_RETRY_DELAY,
)
from .exceptions import TMDbAuthError, TMDbRequestError
from .parsing import ParsedName


@dataclass(frozen=True)
class _Fields:
    """Where TMDb puts things for one kind of title ("movie" or "tv")."""

    year_param: str  # the search's year filter
    title: str
    original_title: str
    date: str
    find_results: str  # the list in a /find response


_FIELDS = {
    "movie": _Fields("year", "title", "original_title", "release_date", "movie_results"),
    "tv": _Fields("first_air_date_year", "name", "original_name", "first_air_date", "tv_results"),
}


@dataclass(frozen=True)
class Match:
    """A TMDb title confirmed for a file."""

    title: str
    year: str
    # Every name the match was scored on (title, original title)
    names: tuple[str, ...] = field(default=(), compare=False)


def _retry_after(exc: HTTPError) -> float | None:
    """Seconds TMDb asks to wait before trying again, if it says."""
    try:
        return float(exc.headers.get("Retry-After", "")) if exc.headers else None
    except ValueError:
        return None


def _get(path: str, params: dict[str, str], api_key: str) -> Any:
    """
    GET a TMDb API path and return the decoded JSON.

    `api_key` may be a v3 API key or a v4 API read access token (a JWT, starting "eyJ").
    Rate limits (429), server errors and network problems are retried a couple of
    times. Raises TMDbAuthError if TMDb rejects the key, TMDbRequestError otherwise.
    """
    params = dict(params)
    headers = {"Accept": "application/json"}
    if api_key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        params["api_key"] = api_key
    url = f"{TMDB_API_URL}{path}?{urlencode(params)}"

    attempt = 1
    while True:
        # S310 guards against file:// and custom schemes; the URL is a fixed https endpoint.
        request = Request(url, headers=headers)  # noqa: S310
        try:
            with urlopen(request, timeout=10) as response:  # noqa: S310
                payload = json.load(response)
        except HTTPError as exc:
            if exc.code == 401:
                raise TMDbAuthError from exc
            retryable = exc.code == 429 or exc.code >= 500
            if not retryable or attempt == TMDB_ATTEMPTS:
                raise TMDbRequestError(str(exc)) from exc
            delay = _retry_after(exc) or TMDB_RETRY_DELAY * 2 ** (attempt - 1)
        except (URLError, TimeoutError) as exc:
            if attempt == TMDB_ATTEMPTS:
                raise TMDbRequestError(str(exc)) from exc
            delay = TMDB_RETRY_DELAY * 2 ** (attempt - 1)
        except ValueError as exc:  # not JSON
            raise TMDbRequestError(str(exc)) from exc
        else:
            return payload
        time.sleep(min(delay, TMDB_MAX_RETRY_DELAY))
        attempt += 1


def search(kind: str, query: str, year: str | None, api_key: str) -> list[dict[str, Any]]:
    """
    Search TMDb for movies (kind "movie") or TV shows (kind "tv") called `query`,
    released or first aired in `year` when given.
    """
    params = {"query": query}
    if year:
        params[_FIELDS[kind].year_param] = year
    results: list[dict[str, Any]] = _get(f"search/{kind}", params, api_key).get("results", [])
    return results


def find(imdb_id: str, api_key: str) -> dict[str, Any]:
    """Look up what an IMDb ID ("tt1375666") points at: movies, TV shows, episodes."""
    found: dict[str, Any] = _get(f"find/{imdb_id}", {"external_source": "imdb_id"}, api_key)
    return found


def alternative_titles(kind: str, tmdb_id: int, api_key: str) -> list[str]:
    """Other names of a movie or TV show, like its title in other countries."""
    data = _get(f"{kind}/{tmdb_id}/alternative_titles", {}, api_key)
    # movies list them under "titles", TV shows under "results"
    entries = data.get("titles") or data.get("results") or []
    return [entry["title"] for entry in entries if entry.get("title")]


def cache_path() -> Path:
    """Where TMDb responses are cached: $REELNAME_CACHE_DIR, else the user cache directory."""
    if custom := os.environ.get("REELNAME_CACHE_DIR"):
        return Path(custom) / "tmdb.sqlite3"
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "reelname" / "tmdb.sqlite3"


def _connect() -> sqlite3.Connection:
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.execute(
        "CREATE TABLE IF NOT EXISTS responses"
        " (key TEXT PRIMARY KEY, fetched_at REAL NOT NULL, body TEXT NOT NULL)"
    )
    return db


def _is_empty(value: Any) -> bool:
    # a /find response is a dict of result lists
    return not (any(value.values()) if isinstance(value, dict) else value)


def _read_cache(key: str) -> Any:
    with closing(_connect()) as db:
        row = db.execute("SELECT fetched_at, body FROM responses WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    fetched_at, body = row
    value = json.loads(body)
    ttl = CACHE_TTL_MISS if _is_empty(value) else CACHE_TTL_HIT
    return value if time.time() - fetched_at < ttl.total_seconds() else None


def _write_cache(key: str, value: Any) -> None:
    with closing(_connect()) as db, db:
        db.execute(
            "INSERT OR REPLACE INTO responses VALUES (?, ?, ?)",
            (key, time.time(), json.dumps(value)),
        )


_cache_warning_shown = False


def _warn_cache_unavailable(exc: Exception) -> None:
    global _cache_warning_shown
    if not _cache_warning_shown:
        click.echo(f"⚠️ TMDb cache unavailable, searching without it: {exc}")
        _cache_warning_shown = True


def _cached(key: list[Any], fetch: Callable[[], Any]) -> Any:
    """
    `fetch()`, answered from the on-disk cache when it holds a fresh response, so
    re-runs and watch mode don't repeat requests. Failed requests aren't cached.
    """
    cache_key = json.dumps(key)
    try:
        cached = _read_cache(cache_key)
    except (OSError, sqlite3.Error) as exc:
        _warn_cache_unavailable(exc)
        return fetch()
    if cached is not None:
        return cached

    value = fetch()
    try:
        _write_cache(cache_key, value)
    except (OSError, sqlite3.Error) as exc:
        _warn_cache_unavailable(exc)
    return value


def cached_search(kind: str, query: str, year: str | None, api_key: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = _cached(
        ["search", kind, query.casefold(), year], lambda: search(kind, query, year, api_key)
    )
    return results


def cached_find(imdb_id: str, api_key: str) -> dict[str, Any]:
    found: dict[str, Any] = _cached(["find", imdb_id], lambda: find(imdb_id, api_key))
    return found


def cached_alternative_titles(kind: str, tmdb_id: int, api_key: str) -> list[str]:
    titles: list[str] = _cached(
        ["alternative_titles", kind, tmdb_id], lambda: alternative_titles(kind, tmdb_id, api_key)
    )
    return titles


def _fold(text: str) -> str:
    """Lower case, without accents or punctuation: "Amélie!" -> "amelie"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return default_process("".join(c for c in decomposed if not unicodedata.combining(c)))


def get_match_score(title: str, candidate: str) -> float:
    """
    Combine three metrics and take the minimum:
      - fuzz.ratio
      - fuzz.token_sort_ratio
      - fuzz.partial_token_sort_ratio
    This punishes missing tokens, order-changes, and trivial substrings.
    Case, accents and punctuation are ignored, so "AMELIE" matches "Amélie".
    """
    return min(
        fuzz.ratio(title, candidate, processor=_fold),
        fuzz.token_sort_ratio(title, candidate, processor=_fold),
        fuzz.partial_token_sort_ratio(title, candidate, processor=_fold),
    )


def best_score(title: str, names: tuple[str, ...] | list[str]) -> float:
    """How well `title` matches the closest of `names`."""
    return max((get_match_score(title, name) for name in names), default=0.0)


def _starts_title(title: str, names: tuple[str, ...]) -> bool:
    """
    `title` is the start of a longer one, as "Birdman" is of "Birdman or (The
    Unexpected Virtue of Ignorance)". Very short titles don't count.
    """
    folded = _fold(title)
    return len(folded) >= 4 and any(_fold(name).startswith(f"{folded} ") for name in names)


def _score(parsed: ParsedName, match: Match) -> float:
    """
    How well a candidate fits. A title that the file name only starts ("Birdman")
    scores just enough to match when the year matches too, so a closer candidate
    still wins. Without a year it's not enough: those need a closer title.
    """
    score = best_score(parsed.title, match.names)
    if score < MATCH_SCORE_WITH_YEAR and _starts_title(parsed.title, match.names):
        return MATCH_SCORE_WITH_YEAR
    return score


def _to_match(result: dict[str, Any], fields: _Fields) -> Match | None:
    names = tuple(n for n in (result.get(fields.title), result.get(fields.original_title)) if n)
    year = (result.get(fields.date) or "")[:4]
    return Match(names[0], year, names) if names and year else None


def _pick(parsed: ParsedName, scored: list[tuple[float, Match]]) -> list[Match]:
    """
    With a year: the best candidate, if it scores well enough. Without: every
    distinct candidate that scores very well (more than one means ambiguous).
    """
    if parsed.year:
        best = max(scored, key=lambda item: item[0], default=None)
        return [best[1]] if best and best[0] >= MATCH_SCORE_WITH_YEAR else []
    return list(dict.fromkeys(m for score, m in scored if score >= MATCH_SCORE_WITHOUT_YEAR))


def find_matches(parsed: ParsedName, api_key: str) -> list[Match]:
    """
    Look the title up on TMDb (TV shows for episodes, movies otherwise), scoring each
    candidate on its title and original title:
      - With a year: the best candidate from that year, if it scores well enough
        (a longer title that starts with the file's title is just enough).
      - Without a year: every distinct candidate that scores very well. More than one
        means the name is ambiguous, like a remake with the same title.
    If no title fits, the first few candidates' alternative titles are tried too,
    so a name in another language still matches ("Gisaengchung" finds "Parasite").
    An empty list means no match.
    """
    kind = "tv" if parsed.is_episode else "movie"
    fields = _FIELDS[kind]

    candidates: list[tuple[dict[str, Any], Match]] = []
    for result in cached_search(kind, parsed.title, parsed.year, api_key):
        match = _to_match(result, fields)
        if match and (not parsed.year or match.year == parsed.year):
            candidates.append((result, match))

    if matches := _pick(parsed, [(_score(parsed, m), m) for _, m in candidates]):
        return matches

    scored = [
        (best_score(parsed.title, cached_alternative_titles(kind, result["id"], api_key)), match)
        for result, match in candidates[:ALTERNATIVE_TITLE_CANDIDATES]
        if isinstance(result.get("id"), int)
    ]
    return _pick(parsed, scored)


def match_imdb_id(imdb_id: str, is_episode: bool, api_key: str) -> Match | None:
    """The movie (or, for an episode, the TV show) an IMDb ID points at, if any."""
    fields = _FIELDS["tv" if is_episode else "movie"]
    results = cached_find(imdb_id, api_key).get(fields.find_results) or []
    return _to_match(results[0], fields) if results else None
