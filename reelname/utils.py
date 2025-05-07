from pathlib import Path
import re
from typing import Optional, Tuple

import aiofiles.os  # type: ignore[import-untyped]
import click
from imdb import Cinemagoer
from thefuzz import fuzz

from .constants import BRACKETED_PATTERN, DOT_YEAR_PATTERN, SPACE_YEAR_PATTERN


def extract_title_and_year(filename: str) -> Optional[Tuple[str, str]]:
    """
    Extract a human-friendly title and year from the filename.
    Tries in order:
      1) bracketed (e.g. 'Name (2023)', 'Name[2023]')
      2) dot-separated (e.g. 'Name.2023.')
      3) space-separated (e.g. 'Name 2023 ...')
    Returns (clean_title, year) or None.
    """
    match = BRACKETED_PATTERN.search(filename)
    if not match:
        match = DOT_YEAR_PATTERN.search(filename)
    if not match:
        match = SPACE_YEAR_PATTERN.search(filename)
    if not match:
        return None

    raw_title = match.group("title").strip()
    year = match.group("year")
    clean_title = re.sub(r"[._]+", " ", raw_title)
    return clean_title, year


def fetch_info_from_imdb(title: str, year: str) -> Tuple[str, str]:
    """
    Look up the title on IMDb via Cinemagoer:
      - Search IMDb for the raw title.
      - Keep only candidates whose year == extracted year.
      - Use fuzzy matching (threshold 60) to pick the best.
      - If found, return (official_title, imdb_year).
      - Otherwise, fall back to the extracted (title, year).
    """
    ia = Cinemagoer()
    results = ia.search_movie(title)

    best_match = None
    best_score = 0
    for movie in results:
        mov_year = movie.get("year")
        if mov_year != int(year):
            continue
        candidate = movie.get("title", "")
        score = fuzz.token_set_ratio(title, candidate)
        if score > best_score:
            best_score = score
            best_match = movie
            if score == 100:
                break

    if best_match and best_score >= 60:
        ia.update(best_match)
        official = best_match.get("title", title)
        imdb_year = str(best_match.get("year", int(year)))
        return official, imdb_year

    return title, year


def rebuild_filename(original: str, official: str, year: str) -> str:
    """
    Reconstruct the filename as:
      OfficialTitle (Year) + suffix.

    - If the filename had a bracketed year (any of (), [], {}, <>),
      preserves the exact bracket type and the following suffix.
    - Otherwise (dot-year or space-year cases), strips leading punctuation
      from the suffix and replaces it with a single space.
    """
    # 1) Detect any bracket pair around the year
    bracket_match = re.search(
        r"(?P<open>[\(\[\{\<])" + re.escape(year) + r"(?P<close>[\)\]\}\>])", original
    )
    if bracket_match:
        open_b = bracket_match.group("open")
        close_b = bracket_match.group("close")
        bracket_text = f"{open_b}{year}{close_b}"
        suffix = original.split(bracket_text, 1)[1]
        return f"{official} {bracket_text}{suffix}"

    # 2) Otherwise split on the year itself
    parts = original.split(year, 1)
    suffix = parts[1]
    suffix_clean = re.sub(r"^[\s._-]+", " ", suffix)
    return f"{official} ({year}){suffix_clean}"


async def _rename_file_async(old_path: str, new_path: str) -> None:
    await aiofiles.os.rename(old_path, new_path)


async def _process_files(directory: Path) -> None:
    """
    Scan `directory` for files, drop any prefix up to the movie title/year,
    skip already-formatted ones, lookup IMDb, and rename accordingly.
    """
    for file in directory.iterdir():
        if not file.is_file():
            continue

        orig = file.name

        # 1) Find the first occurrence of any of our three patterns:
        match = (
            BRACKETED_PATTERN.search(orig)
            or DOT_YEAR_PATTERN.search(orig)
            or SPACE_YEAR_PATTERN.search(orig)
        )
        if not match:
            click.echo(f"⏩ Skipping (no title/year): {orig}")
            continue

        # 2) Drop everything before the match (i.e. strip generic prefix)
        cleaned = orig[match.start():]

        # 3) If it already starts with "Title (Year)" or "Title [Year]" etc., skip
        if BRACKETED_PATTERN.match(cleaned):
            click.echo(f"⏩ Skipping already formatted: {orig}")
            continue

        # 4) Extract title & year from the cleaned string
        raw_title, extracted_year = extract_title_and_year(cleaned)  # this will succeed
        click.echo(f"🔎 Looking up: {raw_title!s} ({extracted_year})")

        # 5) IMDb lookup (returns at least (title, year))
        official_title, imdb_year = fetch_info_from_imdb(raw_title, extracted_year)

        # 6) Rebuild the cleaned filename, then rename the original to that
        new_cleaned = rebuild_filename(cleaned, official_title, imdb_year)
        if new_cleaned != cleaned:
            await _rename_file_async(str(file), str(file.parent / new_cleaned))
            click.echo(f"✅ Renamed: {orig!s} → {new_cleaned!s}")
        else:
            click.echo(f"⏩ Already correct: {orig!s}")
