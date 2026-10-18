from __future__ import annotations

from typing import Any

import pytest

from reelname import tmdb

from .data import YEARLESS_YEAR


class FakeTMDb:
    """
    Stands in for TMDb search. By default it confirms whatever title it's asked
    about, in the year asked for (YEARLESS_YEAR if none). Set `results[query]` to
    return something else.
    """

    def __init__(self) -> None:
        self.results: dict[str, list[dict[str, Any]]] = {}
        self.queries: list[tuple[str, str, str | None]] = []

    def search(
        self, kind: str, query: str, year: str | None, _api_key: str
    ) -> list[dict[str, Any]]:
        self.queries.append((kind, query, year))
        if query in self.results:
            return self.results[query]
        title_field, date_field = (
            ("name", "first_air_date") if kind == "tv" else ("title", "release_date")
        )
        return [{title_field: query, date_field: f"{year or YEARLESS_YEAR}-01-01"}]


@pytest.fixture(autouse=True)
def fake_tmdb(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> FakeTMDb:
    """Keep every test off the network, with its own cache and history."""
    fake = FakeTMDb()
    monkeypatch.setenv("TMDB_API_KEY", "test-key")
    monkeypatch.setenv("REELNAME_CACHE_DIR", str(tmp_path_factory.mktemp("cache")))
    monkeypatch.setenv("REELNAME_DATA_DIR", str(tmp_path_factory.mktemp("data")))
    monkeypatch.setattr(tmdb, "search", fake.search)
    return fake
