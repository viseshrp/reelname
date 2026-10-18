from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any
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
from .exceptions import TMDbAuthError, TMDbNotFoundError, TMDbRequestError
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
    # TMDb's ID for it, for follow-up lookups like episode titles
    tmdb_id: int | None = field(default=None, compare=False)


@dataclass(frozen=True)
class ImdbMatch:
    """What an IMDb ID points at, and for a single episode its season and number."""

    match: Match
    season: int | None = None
    episode: int | None = None


def _retry_after(exc: HTTPError) -> float | None:
    """Seconds TMDb asks to wait before trying again, if it says."""
    try:
        return float(exc.headers.get("Retry-After", "")) if exc.headers else None
    except ValueError:
        return None


def _request(
    path: str, params: dict[str, str], api_key: str, etag: str | None = None
) -> tuple[Any, str | None]:
    """
    One GET to the TMDb API. Returns the decoded JSON and its ETag. With `etag`, the
    JSON is None when TMDb answers 304 Not Modified: the copy with that ETag is current.

    `api_key` may be a v3 API key or a v4 API read access token (a JWT, starting "eyJ").
    Rate limits (429), server errors and network problems are retried a couple of
    times. Raises TMDbAuthError if TMDb rejects the key, TMDbNotFoundError for a 404,
    and TMDbRequestError otherwise.
    """
    params = dict(params)
    headers = {"Accept": "application/json"}
    if api_key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        params["api_key"] = api_key
    if etag:
        headers["If-None-Match"] = etag
    url = f"{TMDB_API_URL}{path}?{urlencode(params)}"

    attempt = 1
    while True:
        # S310 guards against file:// and custom schemes; the URL is a fixed https endpoint.
        request = Request(url, headers=headers)  # noqa: S310
        try:
            with urlopen(request, timeout=10) as response:  # noqa: S310
                payload = json.load(response)
                new_etag = response.headers.get("ETag")
        except HTTPError as exc:
            if exc.code == 304:
                return None, etag
            if exc.code == 401:
                raise TMDbAuthError from exc
            if exc.code == 404:
                raise TMDbNotFoundError(str(exc)) from exc
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
            return payload, new_etag
        time.sleep(min(delay, TMDB_MAX_RETRY_DELAY))
        attempt += 1


def cache_path() -> Path:
    """Where TMDb responses are cached: $REELNAME_CACHE_DIR, else the user cache directory."""
    if custom := os.environ.get("REELNAME_CACHE_DIR"):
        return Path(custom) / "tmdb.sqlite3"
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "reelname" / "tmdb.sqlite3"


@dataclass(frozen=True)
class _Entry:
    """A cached TMDb response."""

    fetched_at: float
    body: Any
    etag: str | None


def _connect() -> sqlite3.Connection:
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.execute(
        "CREATE TABLE IF NOT EXISTS http_cache"
        " (key TEXT PRIMARY KEY, fetched_at REAL NOT NULL, body TEXT NOT NULL, etag TEXT)"
    )
    return db


def _read_entry(key: str) -> _Entry | None:
    with closing(_connect()) as db:
        row = db.execute(
            "SELECT fetched_at, body, etag FROM http_cache WHERE key = ?", (key,)
        ).fetchone()
    return _Entry(row[0], json.loads(row[1]), row[2]) if row else None


def _write_entry(key: str, body: Any, etag: str | None) -> None:
    with closing(_connect()) as db, db:
        db.execute(
            "INSERT OR REPLACE INTO http_cache VALUES (?, ?, ?, ?)",
            (key, time.time(), json.dumps(body), etag),
        )


def _is_empty(body: Any) -> bool:
    """No results: a search that found nothing, a /find with no matches."""
    if isinstance(body, dict):
        if "results" in body:
            return not body["results"]
        lists = [value for value in body.values() if isinstance(value, list)]
        return bool(lists) and not any(lists)
    return not body


def _is_fresh(entry: _Entry) -> bool:
    ttl = CACHE_TTL_MISS if _is_empty(entry.body) else CACHE_TTL_HIT
    return time.time() - entry.fetched_at < ttl.total_seconds()


_cache_warning_shown = False
_stale_warning_shown = False


def _warn_cache_unavailable(exc: Exception) -> None:
    global _cache_warning_shown
    if not _cache_warning_shown:
        click.echo(f"⚠️ TMDb cache unavailable, searching without it: {exc}")
        _cache_warning_shown = True


def _warn_stale(entry: _Entry, exc: Exception) -> None:
    global _stale_warning_shown
    if not _stale_warning_shown:
        cached_on = datetime.fromtimestamp(entry.fetched_at).date().isoformat()
        click.echo(f"⚠️ TMDb unreachable ({exc}), using answers cached as far back as {cached_on}")
        _stale_warning_shown = True


def _get(path: str, params: dict[str, str], api_key: str) -> Any:
    """
    GET a TMDb API path through the on-disk cache, so re-runs and watch mode don't
    repeat requests:
      - A fresh cached answer is used as is (for a week, or a day if it was empty).
      - An expired one is revalidated with its ETag: if it's unchanged, TMDb only
        answers "304 Not Modified".
      - If TMDb can't be reached, an expired answer is used rather than none.
    Failed requests aren't cached.
    """
    # The search text's case doesn't change TMDb's answer
    normalized = {k: v.casefold() if k == "query" else v for k, v in params.items()}
    key = json.dumps([path, sorted(normalized.items())])

    entry = None
    try:
        entry = _read_entry(key)
    except (OSError, sqlite3.Error) as exc:
        _warn_cache_unavailable(exc)
    if entry and _is_fresh(entry):
        return entry.body

    try:
        body, etag = _request(path, params, api_key, entry.etag if entry else None)
    except TMDbNotFoundError:
        raise
    except TMDbRequestError as exc:
        if entry is None:
            raise
        _warn_stale(entry, exc)
        return entry.body
    if body is None and entry is not None:  # 304 Not Modified
        body = entry.body

    try:
        _write_entry(key, body, etag)
    except (OSError, sqlite3.Error) as exc:
        _warn_cache_unavailable(exc)
    return body


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


def tv_show(tmdb_id: int, api_key: str) -> dict[str, Any]:
    """A TV show's details: name, original name, first air date..."""
    details: dict[str, Any] = _get(f"tv/{tmdb_id}", {}, api_key)
    return details


def episode_title(show_id: int, season: int, episode: int, api_key: str) -> str | None:
    """An episode's title, or None if TMDb doesn't list that episode."""
    try:
        data = _get(f"tv/{show_id}/season/{season}/episode/{episode}", {}, api_key)
    except TMDbNotFoundError:
        return None
    title = data.get("name")
    return title if isinstance(title, str) and title else None


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
    tmdb_id = result.get("id") if isinstance(result.get("id"), int) else None
    return Match(names[0], year, names, tmdb_id) if names and year else None


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
    for result in search(kind, parsed.title, parsed.year, api_key):
        match = _to_match(result, fields)
        if match and (not parsed.year or match.year == parsed.year):
            candidates.append((result, match))

    if matches := _pick(parsed, [(_score(parsed, m), m) for _, m in candidates]):
        return matches

    scored = [
        (best_score(parsed.title, alternative_titles(kind, result["id"], api_key)), match)
        for result, match in candidates[:ALTERNATIVE_TITLE_CANDIDATES]
        if isinstance(result.get("id"), int)
    ]
    return _pick(parsed, scored)


def match_imdb_id(imdb_id: str, is_episode: bool, api_key: str) -> ImdbMatch | None:
    """
    What an IMDb ID points at: a movie, or for an episode file a TV show. The ID of a
    single episode leads to its show, with that episode's season and number.
    """
    found = find(imdb_id, api_key)
    movies, shows = found.get("movie_results") or [], found.get("tv_results") or []
    if not is_episode and movies:
        match = _to_match(movies[0], _FIELDS["movie"])
        return ImdbMatch(match) if match else None
    if is_episode and shows:
        match = _to_match(shows[0], _FIELDS["tv"])
        return ImdbMatch(match) if match else None
    if episodes := found.get("tv_episode_results"):
        episode = episodes[0]
        if not isinstance(episode.get("show_id"), int):
            return None
        match = _to_match(tv_show(episode["show_id"], api_key), _FIELDS["tv"])
        if match:
            return ImdbMatch(match, episode.get("season_number"), episode.get("episode_number"))
    return None
