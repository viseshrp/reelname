from __future__ import annotations

from email.message import Message
import io
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from reelname import utils
from reelname.exceptions import TMDbAuthError
from reelname.utils import (
    extract_title_and_year,
    fetch_info_from_tmdb,
    get_match_score,
    rebuild_filename,
)

from .conftest import FakeTMDb
from .data import EXTRACT_CASES, MOVIE_RENAME_CASES

# Bound at import, before the autouse fixture replaces utils.search_tmdb with a fake.
real_search_tmdb = utils.search_tmdb


@pytest.mark.parametrize("filename, expected", EXTRACT_CASES)
def test_extract_title_and_year(filename: str, expected: str) -> None:
    assert extract_title_and_year(filename) == expected


@pytest.mark.parametrize("orig, expected_new", MOVIE_RENAME_CASES)
def test_rebuild_filename_matches_extract(orig: str, expected_new: str) -> None:
    """
    For each movie style filename, extract title+year, then rebuild and
    compare to the expected renamed form.
    """
    # derive title/year from extract_title_and_year
    title, year = extract_title_and_year(orig)
    rebuilt = rebuild_filename(orig, title, year)  # type: ignore
    assert rebuilt == expected_new


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
            ("Inception", "2010"),
        ),
        ([{"title": "Inception", "release_date": ""}, {"title": "Inception"}], (None, None)),
    ],
    ids=["dated-candidate-wins", "only-undated-candidates"],
)
def test_candidates_without_release_year_are_ignored(
    fake_tmdb: FakeTMDb, results: list[dict[str, str]], expected: tuple[str | None, str | None]
) -> None:
    fake_tmdb.results["Inception"] = results
    assert fetch_info_from_tmdb("Inception", "2010", "key") == expected


def _capture_urlopen(seen: dict[str, Any], body: bytes) -> Any:
    def fake_urlopen(request: Request, **_kwargs: Any) -> io.BytesIO:
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        return io.BytesIO(body)

    return fake_urlopen


def test_search_tmdb_sends_v3_key_as_query_param(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(utils, "urlopen", _capture_urlopen(seen, b'{"results": [{"id": 1}]}'))

    assert real_search_tmdb("Inception", "2010", "v3key") == [{"id": 1}]
    assert "query=Inception" in seen["url"]
    assert "year=2010" in seen["url"]
    assert "api_key=v3key" in seen["url"]
    assert seen["auth"] is None


def test_search_tmdb_sends_read_access_token_as_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(utils, "urlopen", _capture_urlopen(seen, b'{"results": []}'))

    assert real_search_tmdb("Inception", "2010", "eyJtoken") == []
    assert "api_key" not in seen["url"]
    assert seen["auth"] == "Bearer eyJtoken"


def test_search_tmdb_rejected_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: Request, **_kwargs: Any) -> io.BytesIO:
        raise HTTPError(request.full_url, 401, "Unauthorized", Message(), None)

    monkeypatch.setattr(utils, "urlopen", fake_urlopen)

    with pytest.raises(TMDbAuthError):
        real_search_tmdb("Inception", "2010", "bad-key")
