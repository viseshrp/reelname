import pytest

from reelname.utils import extract_title_and_year, rebuild_filename

from .data import EXTRACT_CASES, MOVIE_RENAME_CASES


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
