from pathlib import Path

import pytest

from reelname.utils import extract_title_and_year, rebuild_filename


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("Kanchana (2011) Tamil TRUE WEB-DL.mkv", ("Kanchana", "2011")),
        ("The.Studio.2025.S01E07.Casting.mkv", ("The Studio", "2025")),
        ("NoYearHere.mkv", None),
    ],
)
def test_extract_title_and_year(filename: str, expected: tuple) -> None:
    assert extract_title_and_year(filename) == expected


@pytest.mark.parametrize(
    "original, official, year, expected",
    [
        (
            "Title (2020) Something.mkv",
            "Title Official",
            "2020",
            "Title Official (2020) Something.mkv",
        ),
        ("Another Movie (1999).avi", "Another Movie", "1999", "Another Movie (1999).avi"),
    ],
)
def test_rebuild_filename(original: str, official: str, year: str, expected: str) -> None:
    assert rebuild_filename(original, official, year) == expected
