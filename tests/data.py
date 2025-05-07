# tests/data.py

# Files we expect to rename, plus their expected new names
MOVIE_RENAME_CASES = [
    (
        "Inception.2010.1080p.BluRay.x264-REF.mkv",
        "Inception (2010) 1080p.BluRay.x264-REF.mkv",
    ),
    (
        "The.Dark.Knight.2008.720p.WEB-DL.DD5.1.H.264-FLAC-TK.mkv",
        "The Dark Knight (2008) 720p.WEB-DL.DD5.1.H.264-FLAC-TK.mkv",
    ),
    (
        "Parasite.2019.1080p.WEB-DL.DD5.1.H.264-ABCD.mkv",
        "Parasite (2019) 1080p.WEB-DL.DD5.1.H.264-ABCD.mkv",
    ),
    (
        "The.Studio.2025.S01E07.Casting.1080p.ATVP.WEB-DL.DDP5.1.Atmos.H.264-FLUX.mkv",
        "The Studio (2025) S01E07.Casting.1080p.ATVP.WEB-DL.DDP5.1.Atmos.H.264-FLUX.mkv",
    ),
    (
        "The.Dark.Knight[2008]DvDrip-aXXo",
        "The Dark Knight [2008]DvDrip-aXXo",
    ),
    (
        "Anchorman.2.The.Legend.Continues.2013.1080p.BluRay.DDP.5.1.H.265-EDGE2020.mkv",
        "Anchorman 2 The Legend Continues (2013) 1080p.BluRay.DDP.5.1.H.265-EDGE2020.mkv",
    ),
    (
        "The Straight Story 1999 REMASTERED 1080p BluRay HEVC x265 5.1 BONE.mkv",
        "The Straight Story (1999) REMASTERED 1080p BluRay HEVC x265 5.1 BONE.mkv",
    ),
    # **New TamilMV example**:
    (
        "www.1TamilMV.fi - Bajirao Mastani (2015) Tamil HQ HDRip - 1080p - HEVC - x265 - (AAC 2.0) - 1.8GB - ESub.mkv",
        "Bajirao Mastani (2015) Tamil HQ HDRip - 1080p - HEVC - x265 - (AAC 2.0) - 1.8GB - ESub.mkv",
    ),
]

# Filenames that should be skipped because they lack a parsable year
SKIP_CASES = [
    "Some.Random.Show.S02E05.HDTV-XYZ.mkv",
    "JustAFileWithNoYear.txt",
    "LOL. Body.of.Proof.S02E15.HDTV.XviD-LOL.mkv",
    "ASAP. One.Tree.Hill.S09E07.HDTV.x264-ASAP.mkv",
    "2HD. Suburgatory.S01E15.READNFO.HDTV.XviD-2HD.mkv",
    "LOL. The.Mentalist.S04E16.HDTV.x264-LOL.mkv",
]

# Cases for extract_title_and_year (both positive and negative)
EXTRACT_CASES = [
    ("Kanchana (2011) Tamil TRUE WEB-DL.mkv", ("Kanchana", "2011")),
    ("The.Studio.2025.S01E07.Casting.mkv", ("The Studio", "2025")),
    ("NoYearHere.mkv", None),
    ("Citizenfour.2014.720p.WEB-DL.AAC2.0.H.264-NOGRP.mp4", ("Citizenfour", "2014")),
    (
        "The.Movie.Title.2010.REMASTERED.1080p.BluRay.x264-GROUP.mkv",
        ("The Movie Title", "2010"),
    ),
    ("Title.Of.The.Movie.2023.BluRay.x264-GROUP.mkv", ("Title Of The Movie", "2023")),
    (
        "The.Studio.2025.S01E07.Casting.1080p.ATVP.WEB-DL.DDP5.1.Atmos.H.264-FLUX.mkv",
        ("The Studio", "2025"),
    ),
    # And our new TamilMV example:
    (
        "www.1TamilMV.fi - Bajirao Mastani (2015) Tamil HQ HDRip - 1080p - HEVC - x265 - (AAC 2.0) - 1.8GB - ESub.mkv",
        ("Bajirao Mastani", "2015"),
    ),
] + [(fn, None) for fn in SKIP_CASES]
