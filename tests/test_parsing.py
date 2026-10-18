from __future__ import annotations

import os

import pytest

from reelname.parsing import build_stem, format_title, parse_filename

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
        build_stem(parsed, parsed.title, parsed.year or YEARLESS_YEAR) + extension == expected_new
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
