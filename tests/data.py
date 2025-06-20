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
        "The.Dark.Knight[2008]DvDrip-aXXo.avi",
        "The Dark Knight (2008) DvDrip-aXXo.avi",
    ),
    (
        "Anchorman.2.The.Legend.Continues.2013.1080p.BluRay.DDP.5.1.H.265-EDGE2020.mkv",
        "Anchorman 2 The Legend Continues (2013) 1080p.BluRay.DDP.5.1.H.265-EDGE2020.mkv",
    ),
    (
        "The Straight Story 1999 REMASTERED 1080p BluRay HEVC x265 5.1 BONE.mkv",
        "The Straight Story (1999) REMASTERED 1080p BluRay HEVC x265 5.1 BONE.mkv",
    ),
    (
        "www.1TamilMV.fi - Bajirao Mastani (2015) Tamil HQ HDRip - 1080p - HEVC - x265 - (AAC 2.0) - 1.8GB - ESub.mkv",  # noqa: E501
        "Bajirao Mastani (2015) Tamil HQ HDRip - 1080p - HEVC - x265 - (AAC 2.0) - 1.8GB - ESub.mkv",  # noqa: E501
    ),
    (
        "Spider-Man.2002.1080p.BluRay.x264-GROUP.mkv",
        "Spider-Man (2002) 1080p.BluRay.x264-GROUP.mkv",
    ),
    (
        "Inception<2010>720p.x264.AAC.mkv",
        "Inception (2010) 720p.x264.AAC.mkv",
    ),
    (
        "Interstellar{2014}1080p.BluRay.x265-PSA.mkv",
        "Interstellar (2014) 1080p.BluRay.x265-PSA.mkv",
    ),
    (
        "The.Matrix.1999.REMASTERED.BluRay.1080p.DTS-HD.MA.5.1.mkv",
        "The Matrix (1999) REMASTERED.BluRay.1080p.DTS-HD.MA.5.1.mkv",
    ),
    (
        "yts.mx - Anora (2024) 1080p BluRay x265 HEVC-YTS.mp4",
        "Anora (2024) 1080p BluRay x265 HEVC-YTS.mp4",
    ),
    (
        "www.YTS.mx - The.Dark.Knight.2008.1080p.BluRay.x264.mkv",
        "The Dark Knight (2008) 1080p.BluRay.x264.mkv",
    ),
    (
        "rarbg.to - The Matrix 1999 1080p BluRay x264 AAC.mkv",
        "The Matrix (1999) 1080p BluRay x264 AAC.mkv",
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
    ("NoYearHere.mkv", (None, None)),
    ("Citizenfour.2014.720p.WEB-DL.AAC2.0.H.264-NOGRP.mp4", ("Citizenfour", "2014")),
    ("The.Movie.Title.2010.REMASTERED.1080p.BluRay.x264-GROUP.mkv", ("The Movie Title", "2010")),
    ("Title.Of.The.Movie.2023.BluRay.x264-GROUP.mkv", ("Title Of The Movie", "2023")),
    (
        "The.Studio.2025.S01E07.Casting.1080p.ATVP.WEB-DL.DDP5.1.Atmos.H.264-FLUX.mkv",
        ("The Studio", "2025"),
    ),
    (
        "www.1TamilMV.fi - Bajirao Mastani (2015) Tamil HQ HDRip - 1080p - HEVC - x265 - (AAC 2.0) - 1.8GB - ESub.mkv",  # noqa: E501
        ("Bajirao Mastani", "2015"),
    ),
    ("The.Dark.Knight[2008]DvDrip-aXXo.avi", ("The Dark Knight", "2008")),
    ("www.1TamilMV.fi - Bajirao Mastani (2015) Tamil HQ HDRip.mkv", ("Bajirao Mastani", "2015")),
    ("Spider-Man.2002.1080p.BluRay.x264-GROUP.mkv", ("Spider-Man", "2002")),
    ("Inception<2010>720p.x264.AAC.mkv", ("Inception", "2010")),
    ("Interstellar{2014}1080p.BluRay.x265-PSA.mkv", ("Interstellar", "2014")),
    ("The.Matrix.1999.REMASTERED.BluRay.1080p.DTS-HD.MA.5.1.mkv", ("The Matrix", "1999")),
    ("yts.mx - Dune (2021) 1080p BluRay x265 HEVC-YTS.mp4", ("Dune", "2021")),
    # Case where dot-year appears mid-string after prefix
    ("www.YTS.mx - The.Dark.Knight.2008.1080p.BluRay.x264.mkv", ("The Dark Knight", "2008")),
    # Case where space-year appears mid-string after prefix
    ("rarbg.to - The Matrix 1999 1080p BluRay x264 AAC.mkv", ("The Matrix", "1999")),
] + [(fn, (None, None)) for fn in SKIP_CASES]
