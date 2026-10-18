"""
End-to-end runs against the real TMDb API. Skipped unless REELNAME_LIVE_TMDB_API_KEY
holds a TMDb API key or read access token:

    REELNAME_LIVE_TMDB_API_KEY=... uv run pytest -m integration
"""

import os
from pathlib import Path

from click.testing import CliRunner
import pytest

from reelname import tmdb
from reelname.cli import main

# Bound at import, before the autouse fixture replaces tmdb.search with a fake.
real_search = tmdb.search

LIVE_KEY = os.environ.get("REELNAME_LIVE_TMDB_API_KEY")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not LIVE_KEY, reason="set REELNAME_LIVE_TMDB_API_KEY to run"),
]

LIVE_CASES = [
    ("Inception.2010.1080p.BluRay.x264-REF.mkv", "Inception (2010) 1080p.BluRay.x264-REF.mkv"),
    (
        "Anchorman.2.The.Legend.Continues.2013.1080p.BluRay.mkv",
        "Anchorman 2 - The Legend Continues (2013) 1080p.BluRay.mkv",
    ),
    ("Blade.Runner.2049.2017.1080p.BluRay.mkv", "Blade Runner 2049 (2017) 1080p.BluRay.mkv"),
    ("2001.A.Space.Odyssey.1968.1080p.mkv", "2001 - A Space Odyssey (1968) 1080p.mkv"),
    ("Dune.Part.Two.1080p.WEB-DL.mkv", "Dune - Part Two (2024) 1080p.WEB-DL.mkv"),
    (
        "The.Studio.2025.S01E07.Casting.1080p.ATVP.WEB-DL.mkv",
        "The Studio (2025) S01E07.Casting.1080p.ATVP.WEB-DL.mkv",
    ),
    ("Breaking.Bad.S05E14.720p.HDTV.x264.mkv", "Breaking Bad (2008) S05E14.720p.HDTV.x264.mkv"),
]


@pytest.fixture
def live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tmdb, "search", real_search)
    monkeypatch.setenv("TMDB_API_KEY", LIVE_KEY or "")


@pytest.mark.parametrize("orig, expected", LIVE_CASES)
@pytest.mark.usefixtures("live")
def test_live_rename(tmp_path: Path, orig: str, expected: str) -> None:
    (tmp_path / orig).write_bytes(b"")

    result = CliRunner().invoke(main, [str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert [p.name for p in tmp_path.iterdir()] == [expected], result.output


@pytest.mark.usefixtures("live")
def test_live_unknown_title_is_left_alone(tmp_path: Path) -> None:
    name = "Zxqv.Unfindable.Picture.2011.1080p.mkv"
    (tmp_path / name).write_bytes(b"")

    result = CliRunner().invoke(main, [str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert [p.name for p in tmp_path.iterdir()] == [name]
