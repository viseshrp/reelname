from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
import pytest

from reelname.cli import main
from reelname.identify import Identified, identify
from reelname.tmdb import Match

from .conftest import FakeTMDb

INCEPTION = {"movie_results": [{"title": "Inception", "release_date": "2010-07-15"}]}


def names(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


def touch(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def rename(directory: Path) -> str:
    result = CliRunner().invoke(main, [str(directory)])
    assert result.exit_code == 0, result.output
    return result.output


def test_imdb_id_in_file_name(tmp_path: Path, fake_tmdb: FakeTMDb) -> None:
    fake_tmdb.imdb["tt1375666"] = INCEPTION
    movie = touch(tmp_path / "release" / "tt1375666.mkv")

    assert identify(movie, "key") == Identified(Match("Inception", "2010"), "", "IMDb ID tt1375666")


def test_imdb_id_in_own_nfo(tmp_path: Path, fake_tmdb: FakeTMDb) -> None:
    fake_tmdb.imdb["tt1375666"] = INCEPTION
    folder = tmp_path / "release"
    touch(folder / "abc123.mkv")
    touch(folder / "abc123.nfo", "Info: https://www.imdb.com/title/tt1375666/\n")

    output = rename(folder)

    assert names(folder) == ["Inception (2010).mkv", "Inception (2010).nfo"]
    assert "via IMDb ID in abc123.nfo" in output


def test_folder_nfo_only_counts_for_a_single_video(tmp_path: Path, fake_tmdb: FakeTMDb) -> None:
    fake_tmdb.imdb["tt1375666"] = INCEPTION
    folder = tmp_path / "release"
    touch(folder / "abc123.mkv")
    touch(folder / "def456.mkv")
    touch(folder / "info.nfo", "tt1375666")

    rename(folder)

    assert names(folder) == ["abc123.mkv", "def456.mkv", "info.nfo"]


def test_nfo_that_contradicts_the_name_is_ignored(tmp_path: Path, fake_tmdb: FakeTMDb) -> None:
    fake_tmdb.imdb["tt1375666"] = INCEPTION
    fake_tmdb.results["Interstellar"] = []
    folder = tmp_path / "release"
    touch(folder / "Interstellar.2014.mkv")
    touch(folder / "Interstellar.2014.nfo", "tt1375666")

    output = rename(folder)

    assert names(folder) == ["Interstellar.2014.mkv", "Interstellar.2014.nfo"]
    assert "Interstellar.2014.nfo says Inception (2010)" in output


def test_imdb_id_in_folder_name(tmp_path: Path, fake_tmdb: FakeTMDb) -> None:
    fake_tmdb.imdb["tt1375666"] = INCEPTION
    movie = touch(tmp_path / "Inception {imdb-tt1375666}" / "movie.mkv")

    result = identify(movie, "key")

    assert isinstance(result, Identified)
    assert result.match == Match("Inception", "2010")
    assert result.via == "IMDb ID in folder Inception {imdb-tt1375666}"


def test_obfuscated_file_takes_name_from_release_folder(tmp_path: Path) -> None:
    folder = tmp_path / "Inception.2010.1080p.BluRay.x264-GRP"
    touch(folder / "abc123.mkv")
    touch(folder / "abc123-sample.mkv")

    output = rename(folder)

    assert names(folder) == ["Inception (2010) 1080p.BluRay.x264-GRP.mkv", "abc123-sample.mkv"]
    assert "via folder Inception.2010.1080p.BluRay.x264-GRP" in output


def test_folder_with_several_videos_names_none_of_them(tmp_path: Path) -> None:
    folder = tmp_path / "Inception.2010.1080p.BluRay.x264-GRP"
    touch(folder / "abc123.mkv")
    touch(folder / "def456.mkv")

    rename(folder)

    assert names(folder) == ["abc123.mkv", "def456.mkv"]


@pytest.mark.parametrize("folder", ["Downloads", "Movies", "TV Shows", "Videos"])
def test_generic_folder_names_are_not_titles(
    tmp_path: Path, fake_tmdb: FakeTMDb, folder: str
) -> None:
    # a season folder is evidence of a show folder above it, but not of this name
    episode = touch(tmp_path / folder / "Season 1" / "S01E01.mkv")

    assert identify(episode, "key") == "no title found"
    assert fake_tmdb.queries == []


def test_episode_takes_show_from_folder_above_season(tmp_path: Path, fake_tmdb: FakeTMDb) -> None:
    season = tmp_path / "Breaking Bad" / "Season 1"
    touch(season / "S01E01.Pilot.mkv")

    output = rename(season)

    assert names(season) == ["Breaking Bad (2024) S01E01.Pilot.mkv"]
    assert ("tv", "Breaking Bad", None) in fake_tmdb.queries
    assert "via folder Breaking Bad" in output


def test_folder_year_settles_an_ambiguous_name(tmp_path: Path, fake_tmdb: FakeTMDb) -> None:
    fake_tmdb.results["The Lion King"] = [
        {"title": "The Lion King", "release_date": "2019-07-12"},
        {"title": "The Lion King", "release_date": "1994-06-15"},
    ]
    folder = tmp_path / "The.Lion.King.2019.1080p-GRP"
    touch(folder / "The.Lion.King.1080p.mkv")

    rename(folder)

    assert names(folder) == ["The Lion King (2019) 1080p.mkv"]


@pytest.mark.parametrize(
    "file, title",
    [
        ("Movie.A.2010.1080p.mkv", "Movie A"),  # similar title, other year
        ("Heat.1080p.mkv", "Heat"),  # no year, other title
    ],
)
def test_folder_that_contradicts_the_name_is_ignored(
    tmp_path: Path, fake_tmdb: FakeTMDb, file: str, title: str
) -> None:
    fake_tmdb.results[title] = []
    folder = tmp_path / "Movie.B.2012.1080p"
    touch(folder / file)

    output = rename(folder)

    assert names(folder) == [file]
    assert "folder says Movie B (2012)" in output


@pytest.mark.parametrize(
    "path, renamed",
    [
        ("flat/S01E01.mkv", None),  # any folder could be called anything
        ("Breaking Bad/S01E01.mkv", None),  # a show folder, but nothing says so
        ("Breaking Bad/Season 1/S01E01.mkv", "Breaking Bad (2024) S01E01.mkv"),
        ("The.Office.US.S01.720p/S01E03.mkv", "The Office US (2024) S01E03.mkv"),
    ],
)
def test_bare_episode_needs_a_clear_show_folder(
    tmp_path: Path, path: str, renamed: str | None
) -> None:
    episode = touch(tmp_path / path)

    rename(episode.parent)

    assert names(episode.parent) == [renamed or episode.name]


@pytest.mark.parametrize(
    "name, renamed",
    [
        ("05.mkv", "Breaking Bad (2024) S02E05.mkv"),
        ("05 - Pilot.mkv", "Breaking Bad (2024) S02E05 - Pilot.mkv"),
        ("E05.Pilot.720p.mkv", "Breaking Bad (2024) S02E05.Pilot.720p.mkv"),
        ("Episode 5.mkv", "Breaking Bad (2024) S02E05.mkv"),
    ],
)
def test_bare_episode_number_in_season_folder(tmp_path: Path, name: str, renamed: str) -> None:
    season = tmp_path / "Breaking Bad" / "Season 2"
    touch(season / name)

    rename(season)

    assert names(season) == [renamed]


@pytest.mark.parametrize("folder", ["Breaking Bad", "The.Office.US.S01.720p"])
def test_bare_number_outside_a_season_folder_is_not_an_episode(
    tmp_path: Path, fake_tmdb: FakeTMDb, folder: str
) -> None:
    show = tmp_path / folder
    touch(show / "05.mkv")

    rename(show)

    assert names(show) == ["05.mkv"]
    assert fake_tmdb.queries == []


def test_episode_imdb_id_gives_a_file_its_episode(tmp_path: Path, fake_tmdb: FakeTMDb) -> None:
    fake_tmdb.imdb["tt0959621"] = {
        "tv_episode_results": [{"show_id": 1396, "season_number": 1, "episode_number": 1}]
    }
    fake_tmdb.shows[1396] = {"id": 1396, "name": "Breaking Bad", "first_air_date": "2008-01-20"}
    folder = tmp_path / "release"
    touch(folder / "tt0959621.mkv")

    rename(folder)

    assert names(folder) == ["Breaking Bad (2008) S01E01.mkv"]
