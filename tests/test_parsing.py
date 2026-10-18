from __future__ import annotations

import os

import pytest

from reelname.parsing import (
    build_stem,
    episode_rest,
    find_imdb_id,
    fit_stem,
    format_title,
    parse_filename,
    parse_show_folder,
)

from .data import EXTRACT_CASES, MOVIE_RENAME_CASES, TV_RENAME_CASES, YEARLESS_YEAR


@pytest.mark.parametrize("filename, expected", EXTRACT_CASES)
def test_parse_filename(filename: str, expected: tuple[str | None, str | None]) -> None:
    parsed = parse_filename(os.path.splitext(filename)[0])
    assert ((parsed.title, parsed.year) if parsed else (None, None)) == expected


@pytest.mark.parametrize("orig, expected_new", MOVIE_RENAME_CASES + TV_RENAME_CASES)
def test_build_stem_matches_expected(orig: str, expected_new: str) -> None:
    """
    For each filename, parse it, then rebuild it with the parsed title (and year,
    or the year a lookup would add) and compare to the expected renamed form.
    """
    stem, extension = os.path.splitext(orig)
    parsed = parse_filename(stem)
    assert parsed is not None
    assert (
        build_stem(parsed.title, parsed.year or YEARLESS_YEAR, parsed.rest) + extension
        == expected_new
    )


@pytest.mark.parametrize(
    "name, is_episode",
    [
        ("The.Studio.2025.S01E07.Casting", True),
        ("Show.s01.e07", True),
        ("Show.1x07", True),
        ("Movie.2010.1920x1080", False),
        ("Movie.2010.x264", False),
    ],
)
def test_episode_detection(name: str, is_episode: bool) -> None:
    parsed = parse_filename(name)
    assert parsed is not None
    assert parsed.is_episode is is_episode


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Mission: Impossible", "Mission - Impossible"),
        ("Star Wars: Episode IV - A New Hope", "Star Wars - Episode IV - A New Hope"),
        ("2:22", "2.22"),
        ("Inception", "Inception"),
    ],
)
def test_format_title_turns_colons_into_dashes(title: str, expected: str) -> None:
    assert format_title(title) == expected


@pytest.mark.parametrize(
    "name, is_episode",
    [
        ("The.Daily.Show.2024.01.15.Guest", True),
        ("The Daily Show 2024-01-15", True),
        ("Movie.2010.13.45", False),
    ],
)
def test_air_date_marks_an_episode(name: str, is_episode: bool) -> None:
    parsed = parse_filename(name)
    assert parsed is not None
    assert parsed.is_episode is is_episode


def test_slash_in_title_becomes_space() -> None:
    assert format_title("Face/Off") == "Face Off"


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Breaking Bad", ("Breaking Bad", None)),
        ("The Office (2005)", ("The Office", "2005")),
        ("The.Office.US.S01.1080p.WEB-DL", ("The Office US", None)),
        ("Doctor.Who.2005.Season.1", ("Doctor Who", "2005")),
    ],
)
def test_parse_show_folder(name: str, expected: tuple[str, str | None]) -> None:
    show = parse_show_folder(name)
    assert show is not None
    assert (show.title, show.year) == expected


@pytest.mark.parametrize(
    "stem, expected",
    [
        ("S01E07.Pilot", "S01E07.Pilot"),
        ("Breaking.Bad.S01E07", "S01E07"),
        ("NoEpisodeHere", None),
    ],
)
def test_episode_rest(stem: str, expected: str | None) -> None:
    assert episode_rest(stem) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Inception (2010) {imdb-tt1375666}", "tt1375666"),
        ("https://www.imdb.com/title/tt1375666/", "tt1375666"),
        ("tt1375666 and again tt1375666", "tt1375666"),
        ("tt1375666 or tt0816692", None),
        ("att1375666", None),
        ("no id", None),
    ],
)
def test_find_imdb_id(text: str, expected: str | None) -> None:
    assert find_imdb_id(text) == expected


def test_fit_stem_keeps_names_within_255_bytes() -> None:
    stem = "Amélie (2001) " + "1080p.BluRay." * 30
    fitted = fit_stem(stem, ".en.forced.srt")
    assert len((fitted + ".en.forced.srt").encode()) <= 255
    assert fitted.startswith("Amélie (2001) 1080p")
    assert not fitted.endswith(".")
    assert fit_stem("Inception (2010)", ".mkv") == "Inception (2010)"
