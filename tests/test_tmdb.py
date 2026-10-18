from __future__ import annotations

from email.message import Message
import io
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from reelname import tmdb
from reelname.constants import CACHE_TTL_HIT, CACHE_TTL_MISS
from reelname.exceptions import TMDbAuthError, TMDbNotFoundError, TMDbRequestError
from reelname.parsing import ParsedName
from reelname.tmdb import Match, find_matches, get_match_score

from .conftest import FakeTMDb

# Bound at import, before the autouse fixture replaces tmdb._request with a fake.
real_request = tmdb._request

SEARCH_INCEPTION = ("search/movie", {"query": "Inception", "year": "2010"})


class _Response(io.BytesIO):
    """What urlopen returns: a body, and headers."""

    def __init__(self, body: bytes, etag: str | None = None) -> None:
        super().__init__(body)
        self.headers = Message()
        if etag:
            self.headers["ETag"] = etag


def movie(title: str, year: str | None = None) -> ParsedName:
    return ParsedName(title, year, "", is_episode=False)


@pytest.mark.parametrize(
    "title, candidate",
    [
        ("THE DARK KNIGHT", "The Dark Knight"),
        ("the dark knight", "The Dark Knight"),
        ("Spider Man", "Spider-Man"),
    ],
)
def test_match_score_ignores_case_and_punctuation(title: str, candidate: str) -> None:
    assert get_match_score(title, candidate) >= 98


@pytest.mark.parametrize(
    "results, expected",
    [
        (
            [
                {"title": "Inception", "release_date": ""},
                {"title": "Inception"},
                {"title": "Inception", "release_date": "2010-07-15"},
            ],
            [Match("Inception", "2010")],
        ),
        ([{"title": "Inception", "release_date": ""}, {"title": "Inception"}], []),
        ([{"title": "Inception", "release_date": "2011-01-01"}], []),
        ([{"title": "Interstellar", "release_date": "2010-01-01"}], []),
    ],
    ids=["dated-candidate-wins", "only-undated", "wrong-year", "different-title"],
)
def test_find_matches_with_year(
    fake_tmdb: FakeTMDb, results: list[dict[str, str]], expected: list[Match]
) -> None:
    fake_tmdb.results["Inception"] = results
    assert find_matches(movie("Inception", "2010"), "key") == expected


def test_find_matches_without_year_needs_one_clear_candidate(fake_tmdb: FakeTMDb) -> None:
    fake_tmdb.results["Dune Part Two"] = [
        {"title": "Dune: Part Two", "release_date": "2024-02-27"},
        {"title": "Dune: Part Two - Behind the Scenes", "release_date": "2024-05-01"},
    ]
    assert find_matches(movie("Dune Part Two"), "key") == [Match("Dune: Part Two", "2024")]


def test_find_matches_without_year_reports_ambiguity(fake_tmdb: FakeTMDb) -> None:
    fake_tmdb.results["The Lion King"] = [
        {"title": "The Lion King", "release_date": "2019-07-12"},
        {"title": "The Lion King", "release_date": "1994-06-15"},
    ]
    assert find_matches(movie("The Lion King"), "key") == [
        Match("The Lion King", "2019"),
        Match("The Lion King", "1994"),
    ]


def test_find_matches_uses_tv_search_for_episodes(fake_tmdb: FakeTMDb) -> None:
    fake_tmdb.results["The Studio"] = [{"name": "The Studio", "first_air_date": "2025-03-26"}]
    episode = ParsedName("The Studio", "2025", "S01E07", is_episode=True)

    assert find_matches(episode, "key") == [Match("The Studio", "2025")]
    assert fake_tmdb.queries == [("tv", "The Studio", "2025")]


def test_search_is_cached(fake_tmdb: FakeTMDb) -> None:
    find_matches(movie("Inception", "2010"), "key")
    find_matches(movie("INCEPTION", "2010"), "key")
    assert fake_tmdb.queries == [("movie", "Inception", "2010")]


@pytest.mark.parametrize(
    "results, ttl",
    [([{"title": "Inception", "release_date": "2010-07-15"}], CACHE_TTL_HIT), ([], CACHE_TTL_MISS)],
    ids=["hit", "miss"],
)
def test_cache_expires(
    fake_tmdb: FakeTMDb,
    monkeypatch: pytest.MonkeyPatch,
    results: list[dict[str, str]],
    ttl: Any,
) -> None:
    fake_tmdb.results["Inception"] = results
    now = 1_000_000.0
    monkeypatch.setattr(tmdb, "time", SimpleNamespace(time=lambda: now))
    tmdb.search("movie", "Inception", "2010", "key")

    now += ttl.total_seconds() - 1
    tmdb.search("movie", "Inception", "2010", "key")
    assert len(fake_tmdb.queries) == 1, "still fresh"

    now += 2
    tmdb.search("movie", "Inception", "2010", "key")
    assert len(fake_tmdb.queries) == 2, "expired"


def test_unusable_cache_falls_back_to_searching(
    fake_tmdb: FakeTMDb, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("")
    monkeypatch.setenv("REELNAME_CACHE_DIR", str(blocker))
    monkeypatch.setattr(tmdb, "_cache_warning_shown", False)

    assert find_matches(movie("Inception", "2010"), "key") == [Match("Inception", "2010")]
    assert len(fake_tmdb.queries) == 1


def _capture_urlopen(seen: dict[str, Any], body: bytes, etag: str | None = None) -> Any:
    def fake_urlopen(request: Request, **_kwargs: Any) -> _Response:
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        seen["if_none_match"] = request.get_header("If-none-match")
        return _Response(body, etag)

    return fake_urlopen


def test_request_sends_v3_key_as_query_param(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(tmdb, "urlopen", _capture_urlopen(seen, b'{"results": [1]}', 'W/"a"'))

    assert real_request(*SEARCH_INCEPTION, "v3key") == ({"results": [1]}, 'W/"a"')
    assert seen["url"].startswith("https://api.themoviedb.org/3/search/movie?")
    assert "query=Inception" in seen["url"]
    assert "year=2010" in seen["url"]
    assert "api_key=v3key" in seen["url"]
    assert seen["auth"] is None


def test_request_sends_read_access_token_as_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(tmdb, "urlopen", _capture_urlopen(seen, b'{"results": []}'))

    real_request(*SEARCH_INCEPTION, "eyJtoken")
    assert "api_key" not in seen["url"]
    assert seen["auth"] == "Bearer eyJtoken"


def test_search_tv_filters_by_first_air_year(
    fake_tmdb: FakeTMDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def capture(path: str, params: dict[str, str], *_args: Any) -> tuple[Any, None]:
        calls.append((path, params))
        return {"results": []}, None

    monkeypatch.setattr(tmdb, "_request", capture)
    tmdb.search("tv", "The Studio", "2025", "key")
    tmdb.search("tv", "The Studio", None, "key")

    assert calls == [
        ("search/tv", {"query": "The Studio", "first_air_date_year": "2025"}),
        ("search/tv", {"query": "The Studio"}),
    ]


def test_request_rejected_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: Request, **_kwargs: Any) -> io.BytesIO:
        raise HTTPError(request.full_url, 401, "Unauthorized", Message(), None)

    monkeypatch.setattr(tmdb, "urlopen", fake_urlopen)

    with pytest.raises(TMDbAuthError):
        real_request(*SEARCH_INCEPTION, "bad-key")


def test_request_revalidates_with_etag(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def not_modified(request: Request, **_kwargs: Any) -> io.BytesIO:
        seen["if_none_match"] = request.get_header("If-none-match")
        raise HTTPError(request.full_url, 304, "Not Modified", Message(), None)

    monkeypatch.setattr(tmdb, "urlopen", not_modified)

    assert real_request(*SEARCH_INCEPTION, "key", etag='W/"a"') == (None, 'W/"a"')
    assert seen["if_none_match"] == 'W/"a"'


def _expire_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    later = time.time() + CACHE_TTL_HIT.total_seconds() + 60
    monkeypatch.setattr(tmdb, "time", SimpleNamespace(time=lambda: later))


def test_expired_answer_is_revalidated_with_its_etag(
    fake_tmdb: FakeTMDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str | None] = []

    def answer(_path: str, _params: dict[str, str], _key: str, etag: str | None = None) -> Any:
        sent.append(etag)
        if etag:
            return None, etag  # 304 Not Modified
        return {"results": [{"title": "Inception", "release_date": "2010-07-15"}]}, 'W/"a"'

    monkeypatch.setattr(tmdb, "_request", answer)
    first = tmdb.search("movie", "Inception", "2010", "key")
    _expire_cache(monkeypatch)

    assert tmdb.search("movie", "Inception", "2010", "key") == first
    assert sent == [None, 'W/"a"']


def test_expired_answer_is_used_when_tmdb_is_down(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def down(*_args: Any, **_kwargs: Any) -> Any:
        raise TMDbRequestError("timeout")

    first = tmdb.search("movie", "Inception", "2010", "key")
    _expire_cache(monkeypatch)
    monkeypatch.setattr(tmdb, "_request", down)

    assert tmdb.search("movie", "Inception", "2010", "key") == first
    assert "TMDb unreachable" in capsys.readouterr().out
    with pytest.raises(TMDbRequestError):
        tmdb.search("movie", "Never Cached", "2010", "key")


def test_not_found_is_not_answered_from_an_old_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    def gone(*_args: Any, **_kwargs: Any) -> Any:
        raise TMDbNotFoundError

    tmdb.search("movie", "Inception", "2010", "key")
    _expire_cache(monkeypatch)
    monkeypatch.setattr(tmdb, "_request", gone)

    with pytest.raises(TMDbNotFoundError):
        tmdb.search("movie", "Inception", "2010", "key")


def test_match_score_ignores_accents() -> None:
    assert get_match_score("Amelie", "Amélie") >= 98


def test_find_matches_on_original_title(fake_tmdb: FakeTMDb) -> None:
    fake_tmdb.results["Le Fabuleux Destin d Amelie Poulain"] = [
        {
            "title": "Amélie",
            "original_title": "Le Fabuleux Destin d'Amélie Poulain",
            "release_date": "2001-04-25",
        }
    ]
    parsed = movie("Le Fabuleux Destin d Amelie Poulain", "2001")
    assert find_matches(parsed, "key") == [Match("Amélie", "2001")]


def test_find_matches_falls_back_to_alternative_titles(fake_tmdb: FakeTMDb) -> None:
    fake_tmdb.results["Gisaengchung"] = [
        {
            "id": 496243,
            "title": "Parasite",
            "original_title": "기생충",
            "release_date": "2019-05-30",
        }
    ]
    fake_tmdb.alternative[496243] = ["Gisaengchung", "Parasite: Black and White"]

    assert find_matches(movie("Gisaengchung", "2019"), "key") == [Match("Parasite", "2019")]
    assert ("alternative_titles", "movie", "496243") in fake_tmdb.queries


def test_alternative_titles_only_when_no_title_fits(fake_tmdb: FakeTMDb) -> None:
    fake_tmdb.results["Inception"] = [
        {"id": 27205, "title": "Inception", "release_date": "2010-07-15"}
    ]

    find_matches(movie("Inception", "2010"), "key")

    assert not any(query[0] == "alternative_titles" for query in fake_tmdb.queries)


@pytest.mark.parametrize("is_episode, expected", [(False, "Inception"), (True, "The Office")])
def test_match_imdb_id_picks_the_files_kind(
    fake_tmdb: FakeTMDb, is_episode: bool, expected: str
) -> None:
    fake_tmdb.imdb["tt0000001"] = {
        "movie_results": [{"title": "Inception", "release_date": "2010-07-15"}],
        "tv_results": [{"name": "The Office", "first_air_date": "2005-03-24"}],
    }
    hit = tmdb.match_imdb_id("tt0000001", is_episode, "key")
    assert hit is not None
    assert hit.match.title == expected


@pytest.mark.parametrize("is_episode", [False, True])
def test_episode_imdb_id_leads_to_its_show(fake_tmdb: FakeTMDb, is_episode: bool) -> None:
    fake_tmdb.imdb["tt0959621"] = {
        "tv_episode_results": [{"show_id": 1396, "season_number": 1, "episode_number": 1}]
    }
    fake_tmdb.shows[1396] = {"id": 1396, "name": "Breaking Bad", "first_air_date": "2008-01-20"}

    assert tmdb.match_imdb_id("tt0959621", is_episode, "key") == tmdb.ImdbMatch(
        Match("Breaking Bad", "2008"), season=1, episode=1
    )


def test_match_imdb_id_is_cached(fake_tmdb: FakeTMDb) -> None:
    fake_tmdb.imdb["tt1375666"] = {
        "movie_results": [{"title": "Inception", "release_date": "2010-07-15"}]
    }
    tmdb.match_imdb_id("tt1375666", False, "key")
    tmdb.match_imdb_id("tt1375666", False, "key")
    assert fake_tmdb.queries == [("find", "tt1375666", None)]


def _http_error(code: int, retry_after: str | None = None) -> HTTPError:
    headers = Message()
    if retry_after:
        headers["Retry-After"] = retry_after
    return HTTPError("https://api.themoviedb.org/3/search/movie", code, "error", headers, None)


def _flaky_urlopen(failures: list[Exception], calls: list[str]) -> Any:
    """Raise each of `failures` in turn, then answer with an empty result list."""

    def fake_urlopen(request: Request, **_kwargs: Any) -> _Response:
        calls.append(request.full_url)
        if failures:
            raise failures.pop(0)
        return _Response(b'{"results": []}')

    return fake_urlopen


@pytest.mark.parametrize(
    "failures, expected_sleeps",
    [
        ([_http_error(429, retry_after="3")], [3.0]),
        ([_http_error(503), _http_error(502)], [1.0, 2.0]),
        ([URLError("connection reset")], [1.0]),
        ([_http_error(429, retry_after="120")], [10.0]),
    ],
    ids=["rate-limited", "server-errors", "network", "long-retry-after-capped"],
)
def test_requests_are_retried(
    monkeypatch: pytest.MonkeyPatch, failures: list[Exception], expected_sleeps: list[float]
) -> None:
    calls: list[str] = []
    sleeps: list[float] = []
    monkeypatch.setattr(tmdb, "urlopen", _flaky_urlopen(list(failures), calls))
    monkeypatch.setattr(tmdb, "time", SimpleNamespace(sleep=sleeps.append, time=lambda: 0.0))

    assert real_request(*SEARCH_INCEPTION, "key") == ({"results": []}, None)
    assert sleeps == expected_sleeps
    assert len(calls) == len(expected_sleeps) + 1


@pytest.mark.parametrize(
    "failures",
    [
        [_http_error(503), _http_error(503), _http_error(503)],
        [_http_error(404)],
    ],
    ids=["gives-up-after-three", "no-retry-on-404"],
)
def test_requests_fail_eventually(
    monkeypatch: pytest.MonkeyPatch, failures: list[Exception]
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(tmdb, "urlopen", _flaky_urlopen(list(failures), calls))
    monkeypatch.setattr(tmdb, "time", SimpleNamespace(sleep=lambda _s: None, time=lambda: 0.0))

    with pytest.raises(TMDbRequestError):
        real_request(*SEARCH_INCEPTION, "key")
    assert len(calls) == len(failures)


BIRDMAN = "Birdman or (The Unexpected Virtue of Ignorance)"


@pytest.mark.parametrize(
    "query, year, title, matches",
    [
        ("Birdman", "2014", BIRDMAN, True),
        ("Birdman", None, BIRDMAN, False),  # without a year, a prefix alone is too weak
        ("Bird", "2014", BIRDMAN, False),  # not a whole word
        ("Up", "2009", "Up in the Air", False),  # too short to count
    ],
)
def test_find_matches_accepts_a_longer_title_starting_with_the_name(
    fake_tmdb: FakeTMDb, query: str, year: str | None, title: str, matches: bool
) -> None:
    fake_tmdb.results[query] = [{"title": title, "release_date": f"{year or '2014'}-10-17"}]
    expected = [Match(title, year or "2014")] if matches else []
    assert find_matches(movie(query, year), "key") == expected


def test_closer_title_beats_a_longer_one(fake_tmdb: FakeTMDb) -> None:
    fake_tmdb.results["Alien"] = [
        {"title": "Alien Nation", "release_date": "1979-01-01"},
        {"title": "Alien", "release_date": "1979-05-25"},
    ]
    assert find_matches(movie("Alien", "1979"), "key") == [Match("Alien", "1979")]
