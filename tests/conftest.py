from __future__ import annotations

from typing import Any

import pytest

from reelname import tmdb
from reelname.exceptions import TMDbNotFoundError

from .data import YEARLESS_YEAR


class FakeTMDb:
    """
    Stands in for the TMDb API, behind reelname's cache. By default a search
    confirms whatever title it's asked about, in the year asked for (YEARLESS_YEAR
    if none). Set `results[query]` to return something else.
    """

    def __init__(self) -> None:
        self.results: dict[str, list[dict[str, Any]]] = {}
        self.queries: list[tuple[str, str, str | None]] = []
        # IMDb ID -> /find response, TMDb ID -> alternative titles or TV show details,
        # and (show ID, season, episode) -> episode title
        self.imdb: dict[str, dict[str, Any]] = {}
        self.alternative: dict[int, list[str]] = {}
        self.shows: dict[int, dict[str, Any]] = {}
        self.episodes: dict[tuple[int, int, int], str] = {}

    def search(self, kind: str, query: str, year: str | None) -> list[dict[str, Any]]:
        self.queries.append((kind, query, year))
        if query in self.results:
            return self.results[query]
        title_field, date_field = (
            ("name", "first_air_date") if kind == "tv" else ("title", "release_date")
        )
        return [{title_field: query, date_field: f"{year or YEARLESS_YEAR}-01-01"}]

    def request(
        self, path: str, params: dict[str, str], _api_key: str, _etag: str | None = None
    ) -> tuple[Any, str | None]:
        parts = path.split("/")
        if parts[0] == "search":
            year = params.get("year") or params.get("first_air_date_year")
            return {"results": self.search(parts[1], params["query"], year)}, None
        if parts[0] == "find":
            self.queries.append(("find", parts[1], None))
            return self.imdb.get(parts[1], {"movie_results": [], "tv_results": []}), None
        if parts[-1] == "alternative_titles":
            self.queries.append(("alternative_titles", parts[0], parts[1]))
            titles = [{"title": t} for t in self.alternative.get(int(parts[1]), [])]
            return {"titles" if parts[0] == "movie" else "results": titles}, None
        if parts[0] == "tv" and len(parts) == 2:
            self.queries.append(("show", parts[1], None))
            if int(parts[1]) not in self.shows:
                raise TMDbNotFoundError
            return self.shows[int(parts[1])], None
        if parts[0] == "tv" and "episode" in parts:
            show, season, episode = int(parts[1]), int(parts[3]), int(parts[5])
            self.queries.append(("episode", parts[1], f"S{season}E{episode}"))
            if (show, season, episode) not in self.episodes:
                raise TMDbNotFoundError
            return {"name": self.episodes[(show, season, episode)]}, None
        raise AssertionError(path)  # a TMDb request the fake doesn't know


@pytest.fixture(autouse=True)
def fake_tmdb(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> FakeTMDb:
    """Keep every test off the network, with its own cache and history."""
    fake = FakeTMDb()
    monkeypatch.setenv("TMDB_API_KEY", "test-key")
    monkeypatch.setenv("REELNAME_CACHE_DIR", str(tmp_path_factory.mktemp("cache")))
    monkeypatch.setenv("REELNAME_DATA_DIR", str(tmp_path_factory.mktemp("data")))
    monkeypatch.setattr(tmdb, "_request", fake.request)
    monkeypatch.setattr(tmdb, "_stale_warning_shown", False)
    return fake
