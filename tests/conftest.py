from __future__ import annotations

from typing import Any

import pytest

from reelname import utils


class FakeTMDb:
    """
    Stands in for TMDb search. By default it confirms whatever title and year
    it is asked about; set `results[title]` to return something else.
    """

    def __init__(self) -> None:
        self.results: dict[str, list[dict[str, Any]]] = {}
        self.queries: list[tuple[str, str]] = []

    def search(self, title: str, year: str, _api_key: str) -> list[dict[str, Any]]:
        self.queries.append((title, year))
        return self.results.get(title, [{"title": title, "release_date": f"{year}-01-01"}])


@pytest.fixture(autouse=True)
def fake_tmdb(monkeypatch: pytest.MonkeyPatch) -> FakeTMDb:
    """Keep every test off the network."""
    fake = FakeTMDb()
    monkeypatch.setenv("TMDB_API_KEY", "test-key")
    monkeypatch.setattr(utils, "search_tmdb", fake.search)
    return fake
