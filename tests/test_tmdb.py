from __future__ import annotations

from email.message import Message
import io
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from reelname import tmdb
from reelname.constants import CACHE_TTL_HIT, CACHE_TTL_MISS
from reelname.exceptions import TMDbAuthError
from reelname.parsing import ParsedName
from reelname.tmdb import Match, find_matches, get_match_score

from .conftest import FakeTMDb

# Bound at import, before the autouse fixture replaces tmdb.search with a fake.
real_search = tmdb.search


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
def test_cached_search_expires(
    fake_tmdb: FakeTMDb,
    monkeypatch: pytest.MonkeyPatch,
    results: list[dict[str, str]],
    ttl: Any,
) -> None:
    fake_tmdb.results["Inception"] = results
    now = 1_000_000.0
    monkeypatch.setattr(tmdb, "time", SimpleNamespace(time=lambda: now))
    tmdb.cached_search("movie", "Inception", "2010", "key")

    now += ttl.total_seconds() - 1
    tmdb.cached_search("movie", "Inception", "2010", "key")
    assert len(fake_tmdb.queries) == 1, "still fresh"

    now += 2
    tmdb.cached_search("movie", "Inception", "2010", "key")
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


def _capture_urlopen(seen: dict[str, Any], body: bytes) -> Any:
    def fake_urlopen(request: Request, **_kwargs: Any) -> io.BytesIO:
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        return io.BytesIO(body)

    return fake_urlopen


def test_search_sends_v3_key_as_query_param(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(tmdb, "urlopen", _capture_urlopen(seen, b'{"results": [{"id": 1}]}'))

    assert real_search("movie", "Inception", "2010", "v3key") == [{"id": 1}]
    assert seen["url"].startswith("https://api.themoviedb.org/3/search/movie?")
    assert "query=Inception" in seen["url"]
    assert "year=2010" in seen["url"]
    assert "api_key=v3key" in seen["url"]
    assert seen["auth"] is None


def test_search_sends_read_access_token_as_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(tmdb, "urlopen", _capture_urlopen(seen, b'{"results": []}'))

    assert real_search("movie", "Inception", "2010", "eyJtoken") == []
    assert "api_key" not in seen["url"]
    assert seen["auth"] == "Bearer eyJtoken"


def test_search_tv_filters_by_first_air_year(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(tmdb, "urlopen", _capture_urlopen(seen, b'{"results": []}'))

    real_search("tv", "The Studio", "2025", "key")
    assert seen["url"].startswith("https://api.themoviedb.org/3/search/tv?")
    assert "first_air_date_year=2025" in seen["url"]

    real_search("tv", "The Studio", None, "key")
    assert "first_air_date_year" not in seen["url"]


def test_search_rejected_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: Request, **_kwargs: Any) -> io.BytesIO:
        raise HTTPError(request.full_url, 401, "Unauthorized", Message(), None)

    monkeypatch.setattr(tmdb, "urlopen", fake_urlopen)

    with pytest.raises(TMDbAuthError):
        real_search("movie", "Inception", "2010", "bad-key")
