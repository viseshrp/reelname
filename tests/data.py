# The fake TMDb in conftest.py confirms every title it's asked about. Names without a
# year get this release year back.
YEARLESS_YEAR = "2024"

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
    # Year right before the extension: the extension must survive
    ("Inception.2010.mkv", "Inception (2010).mkv"),
    ("Inception [2010].mkv", "Inception (2010).mkv"),
    # A title containing "trailer" is not a trailer
    (
        "Trailer.Park.Boys.The.Movie.2006.DVDRip.mkv",
        "Trailer Park Boys The Movie (2006) DVDRip.mkv",
    ),
    # A subtitle with no video next to it is renamed on its own
    (
        "Inception.2010.1080p.BluRay.x264-REF.en.srt",
        "Inception (2010) 1080p.BluRay.x264-REF.en.srt",
    ),
    # Numbers that look like years: titles that are years, and years in the future
    ("2001.A.Space.Odyssey.1968.1080p.BluRay.mkv", "2001 A Space Odyssey (1968) 1080p.BluRay.mkv"),
    ("1917.2019.1080p.WEB-DL.mkv", "1917 (2019) 1080p.WEB-DL.mkv"),
    ("Blade.Runner.2049.2017.1080p.BluRay.mkv", "Blade Runner 2049 (2017) 1080p.BluRay.mkv"),
    # No year in the name: the title ends where the release info starts
    ("Dune.Part.Two.1080p.WEB-DL.mkv", f"Dune Part Two ({YEARLESS_YEAR}) 1080p.WEB-DL.mkv"),
    # Title words that are also release info stay in the title
    ("Uncut.Gems.2019.1080p.mkv", "Uncut Gems (2019) 1080p.mkv"),
]

# TV episodes: the show name ends at the episode marker, which starts the rest
TV_RENAME_CASES = [
    (
        "The.Studio.2025.S01E07.Casting.1080p.ATVP.WEB-DL.DDP5.1.Atmos.H.264-FLUX.mkv",
        "The Studio (2025) S01E07.Casting.1080p.ATVP.WEB-DL.DDP5.1.Atmos.H.264-FLUX.mkv",
    ),
    ("Doctor.Who.2005.1x01.Rose.mkv", "Doctor Who (2005) 1x01.Rose.mkv"),
    (
        "Some.Random.Show.S02E05.HDTV-XYZ.mkv",
        f"Some Random Show ({YEARLESS_YEAR}) S02E05.HDTV-XYZ.mkv",
    ),
    # A leading release group ("LOL. ") is dropped when the name ends with the same group
    (
        "LOL. Body.of.Proof.S02E15.HDTV.XviD-LOL.mkv",
        f"Body of Proof ({YEARLESS_YEAR}) S02E15.HDTV.XviD-LOL.mkv",
    ),
    (
        "2HD. Suburgatory.S01E15.READNFO.HDTV.XviD-2HD.mkv",
        f"Suburgatory ({YEARLESS_YEAR}) S01E15.READNFO.HDTV.XviD-2HD.mkv",
    ),
]

# Media files with nothing to look up
SKIP_CASES = [
    "JustAFileWithNoYear.txt",
    "NoYearHere.mkv",
    "holiday_video_03.mp4",
]

# Files that have a title and year but must not be renamed: not media, or a sample/trailer
NON_MEDIA_CASES = [
    "Invoice 2023 final.pdf",
    "Inception.2010.1080p.BluRay.x264-REF.nfo",
    "Inception.2010.1080p.BluRay.x264-REF-sample.mkv",
    "sample-inception.2010.1080p.mkv",
    "Inception (2010) [Trailer].mp4",
]

# Cases for parse_filename: (name, (title, year)), (None, None) when there's no title
EXTRACT_CASES = [
    ("Kanchana (2011) Tamil TRUE WEB-DL.mkv", ("Kanchana", "2011")),
    ("The.Studio.2025.S01E07.Casting.mkv", ("The Studio", "2025")),
    ("NoYearHere.mkv", (None, None)),
    ("Citizenfour.2014.720p.WEB-DL.AAC2.0.H.264-NOGRP.mp4", ("Citizenfour", "2014")),
    ("The.Movie.Title.2010.REMASTERED.1080p.BluRay.x264-GROUP.mkv", ("The Movie Title", "2010")),
    ("Title.Of.The.Movie.2023.BluRay.x264-GROUP.mkv", ("Title Of The Movie", "2023")),
    (
        "www.1TamilMV.fi - Bajirao Mastani (2015) Tamil HQ HDRip - 1080p - HEVC - x265 - (AAC 2.0) - 1.8GB - ESub.mkv",  # noqa: E501
        ("Bajirao Mastani", "2015"),
    ),
    ("The.Dark.Knight[2008]DvDrip-aXXo.avi", ("The Dark Knight", "2008")),
    ("Spider-Man.2002.1080p.BluRay.x264-GROUP.mkv", ("Spider-Man", "2002")),
    ("Inception<2010>720p.x264.AAC.mkv", ("Inception", "2010")),
    ("Interstellar{2014}1080p.BluRay.x265-PSA.mkv", ("Interstellar", "2014")),
    ("yts.mx - Dune (2021) 1080p BluRay x265 HEVC-YTS.mp4", ("Dune", "2021")),
    ("rarbg.to - The Matrix 1999 1080p BluRay x264 AAC.mkv", ("The Matrix", "1999")),
    ("(500).Days.of.Summer.2009.1080p.mkv", ("(500) Days of Summer", "2009")),
    ("Charlottes.Web.2006.1080p.mkv", ("Charlottes Web", "2006")),
    ("Cam.2018.1080p.mkv", ("Cam", "2018")),
    # "1080" is not a year, so the title runs up to the first release info
    ("Some Movie 1080 x264.mkv", ("Some Movie 1080", None)),
    ("ASAP. One.Tree.Hill.S09E07.HDTV.x264-ASAP.mkv", ("One Tree Hill", None)),
    ("LOL. The.Mentalist.S04E16.HDTV.x264-LOL.mkv", ("The Mentalist", None)),
    # A group prefix that the name doesn't end with is part of the title
    ("Mr. Robot.S01E01.mkv", ("Mr Robot", None)),
    ("S01E01.mkv", (None, None)),
] + [(fn, (None, None)) for fn in SKIP_CASES]
