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

# Bound at import, before the autouse fixture replaces them with fakes.
REAL_REQUESTS = {name: getattr(tmdb, name) for name in ("search", "find", "alternative_titles")}

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
    # the file name is only the start of the title
    (
        "Birdman.2014.1080p.BluRay.mkv",
        "Birdman or (The Unexpected Virtue of Ignorance) (2014) 1080p.BluRay.mkv",
    ),
    ("Face.Off.1997.1080p.mkv", "Face Off (1997) 1080p.mkv"),
    ("Amelie.2001.1080p.mkv", "Amélie (2001) 1080p.mkv"),
    # found through TMDb's alternative titles
    ("Gisaengchung.2019.1080p.mkv", "Parasite (2019) 1080p.mkv"),
    ("tt1375666.mkv", "Inception (2010).mkv"),
]

# (folder, file) -> the file's new name: names that only make sense with their folder
LIVE_FOLDER_CASES = [
    (
        "Inception.2010.1080p.BluRay.x264-GRP",
        "abc123.mkv",
        "Inception (2010) 1080p.BluRay.x264-GRP.mkv",
    ),
    ("Breaking Bad/Season 1", "S01E01.Pilot.mkv", "Breaking Bad (2008) S01E01.Pilot.mkv"),
    ("The.Office.2005.S01.720p", "The.Office.S01E02.720p.mkv", "The Office (2005) S01E02.720p.mkv"),
]


@pytest.fixture
def live(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, request in REAL_REQUESTS.items():
        monkeypatch.setattr(tmdb, name, request)
    monkeypatch.setenv("TMDB_API_KEY", LIVE_KEY or "")


@pytest.mark.parametrize("orig, expected", LIVE_CASES)
@pytest.mark.usefixtures("live")
def test_live_rename(tmp_path: Path, orig: str, expected: str) -> None:
    (tmp_path / orig).write_bytes(b"")

    result = CliRunner().invoke(main, [str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert [p.name for p in tmp_path.iterdir()] == [expected], result.output


@pytest.mark.parametrize("folder, orig, expected", LIVE_FOLDER_CASES)
@pytest.mark.usefixtures("live")
def test_live_rename_using_folder(tmp_path: Path, folder: str, orig: str, expected: str) -> None:
    (tmp_path / folder).mkdir(parents=True)
    (tmp_path / folder / orig).write_bytes(b"")

    result = CliRunner().invoke(main, [str(tmp_path / folder)])

    assert result.exit_code == 0, result.output
    assert [p.name for p in (tmp_path / folder).iterdir()] == [expected], result.output


@pytest.mark.usefixtures("live")
def test_live_imdb_id_in_nfo(tmp_path: Path) -> None:
    (tmp_path / "xyz.mkv").write_bytes(b"")
    (tmp_path / "xyz.nfo").write_text("https://www.imdb.com/title/tt0816692/\n")

    result = CliRunner().invoke(main, [str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "Interstellar (2014).mkv",
        "Interstellar (2014).nfo",
    ]


@pytest.mark.usefixtures("live")
def test_live_unknown_title_is_left_alone(tmp_path: Path) -> None:
    name = "Zxqv.Unfindable.Picture.2011.1080p.mkv"
    (tmp_path / name).write_bytes(b"")

    result = CliRunner().invoke(main, [str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert [p.name for p in tmp_path.iterdir()] == [name]
