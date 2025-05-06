import pytest

from reelname.utils import extract_title_and_year, rebuild_filename


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("Kanchana (2011) Tamil TRUE WEB-DL.mkv", ("Kanchana", "2011")),
        ("The.Studio.2025.S01E07.Casting.mkv", ("The Studio", "2025")),
        ("NoYearHere.mkv", None),
        ("Citizenfour.2014.720p.WEB-DL.AAC2.0.H.264-NOGRP.mp4", ("Citizenfour", "2014")),
        (
            "The.Movie.Title.2010.REMASTERED.1080p.BluRay.x264-GROUP.mkv",
            ("The Movie Title", "2010"),
        ),
        ("Title.Of.The.Movie.2023.BluRay.x264-GROUP.mkv", ("Title Of The Movie", "2023")),
        # Mixed TV/movie pattern with year
        (
            "The.Studio.2025.S01E07.Casting.1080p.ATVP.WEB-DL.DDP5.1.Atmos.H.264-FLUX.mkv",
            ("The Studio", "2025"),
        ),
        # Pure-TV patterns (no year) should be skipped
        ("LOL. Body.of.Proof.S02E15.HDTV.XviD-LOL.mkv", None),
        ("ASAP. One.Tree.Hill.S09E07.HDTV.x264-ASAP.mkv", None),
        ("2HD. Suburgatory.S01E15.READNFO.HDTV.XviD-2HD.mkv", None),
        ("LOL. The.Mentalist.S04E16.HDTV.x264-LOL.mkv", None),
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
