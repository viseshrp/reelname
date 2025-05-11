from pathlib import Path
import re
from typing import Optional, Tuple

import aiofiles.os  # type: ignore[import-untyped]
import click
from imdb import Cinemagoer
from rapidfuzz import fuzz

from .constants import (
    BRACKETED_PATTERN,
    DOT_YEAR_PATTERN,
    INVALID_FILENAME_CHARS,
    SPACE_YEAR_PATTERN,
)


def extract_title_and_year(filename: str) -> Optional[Tuple[str, str]]:
    """
    Try in order:
      1) 'Title (YYYY)'
      2) 'Title.YYYY.'
      3) 'Title YYYY '
    on the raw filename.

    Then, if the captured raw_title contains " - ", drop everything before that.
    Finally, replace dots/underscores with spaces.
    """
    for pat in (BRACKETED_PATTERN, DOT_YEAR_PATTERN, SPACE_YEAR_PATTERN):
        m = pat.search(filename)
        if not m:
            continue

        raw_title = m.group("title").strip()
        year = m.group("year")

        # Drop any leading junk if there's a " - " delimiter
        if " - " in raw_title:
            raw_title = raw_title.split(" - ", 1)[-1].strip()

        # Normalize dot/underscore separators to spaces
        title = re.sub(r"[._]+", " ", raw_title).strip()
        return title, year

    return None


def get_match_score(title: str, candidate: str) -> float:
    """
    Combine three metrics and take the minimum:
      - fuzz.ratio
      - fuzz.token_sort_ratio
      - fuzz.partial_token_sort_ratio
    This punishes missing tokens, order-changes, and trivial substrings.
    """
    return min(
        fuzz.ratio(title, candidate),
        fuzz.token_sort_ratio(title, candidate),
        fuzz.partial_token_sort_ratio(title, candidate),
    )


def fetch_info_from_imdb(title: str, year: str) -> Tuple[str, str]:
    """
    Look up the title on IMDb via Cinemagoer:
      - Search IMDb for the raw title.
      - Use fuzzy matching to pick the best.
      - If found, return (official_title, imdb_year).
      - Otherwise, fall back to the extracted (title, year).
    """
    ia = Cinemagoer()
    results = ia.search_movie(f"{title} {year}")

    best_match = None
    best_score = 0.0
    for movie in results:
        candidate = movie.get("title", "")
        score = get_match_score(title, candidate)
        if score > best_score:
            best_score = score
            best_match = movie
            if score >= 98.0:
                break

    if best_match and best_score >= 80:
        ia.update(best_match)  # makes a second request to get detailed info.
        imdb_title = best_match.get("title")
        imdb_year = str(best_match.get("year"))
        if imdb_title and imdb_year:  # return the fixed title and year
            click.echo(f"🔎 Found: {imdb_title} ({imdb_year})")
            return imdb_title, imdb_year

    return title, year


def _sanitize_filename(name: str) -> str:
    """
    Remove any characters that are invalid in filenames on Windows (and many other OSes).
    """
    return INVALID_FILENAME_CHARS.sub("", name).strip()


def rebuild_filename(original: str, title: str, year: str) -> str:
    """
    Given a cleaned filename starting at the title/year, reconstruct it as:
      {title} ({year}){suffix}

    Always uses parentheses around the year, and strips any leftover
    punctuation or brackets before the suffix.
    """
    # 1) Find the first occurrence of the year in the string
    idx = original.find(year)
    if idx == -1:
        # (shouldn't happen if caller extracted title/year correctly)
        file_name = f"{title} ({year})"
    else:
        # 2) Take everything after that year
        suffix = original[idx + len(year) :]

        # 3) Strip any leading punctuation/brackets/whitespace from the suffix,
        #    replacing it with a single space (if there is any suffix at all).
        suffix_clean = re.sub(r"^[\s._\-\[\](){}<]+", " ", suffix)

        # 4) Build the new filename
        file_name = f"{title} ({year}){suffix_clean}"

    return _sanitize_filename(file_name)


async def _rename_file_async(old_path: str, new_path: str) -> None:
    await aiofiles.os.rename(old_path, new_path)


async def _process_files(directory: Path) -> None:
    """
    Scan `directory` for files, skip ones without title/year,
    skip already-formatted ones, lookup IMDb, and rename.
    """
    for file in directory.iterdir():
        if not file.is_file():
            continue

        raw_filename = file.name

        # 1) extract_title_and_year now handles prefix-stripping
        info = extract_title_and_year(raw_filename)
        if not info:
            click.echo(f"⏩ Skipping (no title/year): {raw_filename}")
            continue
        title, year = info

        # 2) skip files already beginning with “Title (Year)”
        formatted_prefix = f"{title} ({year})"
        if raw_filename.startswith(formatted_prefix):
            click.echo(f"⏩ Skipping already formatted: {raw_filename}")
            continue

        click.echo(f"🔎 Looking up: {title} ({year})")
        imdb_title, imdb_year = fetch_info_from_imdb(title, year)

        # 3) rebuild_filename expects the *cleaned* substring:
        #    we re-slice from the first occurrence of the year
        #    so that rebuild_filename sees “Title(…)suffix”
        start = raw_filename.find(year)
        cleaned = raw_filename[start:]

        new_name = rebuild_filename(cleaned, imdb_title, imdb_year)
        if new_name != cleaned:
            # rename the *original* file to the cleaned new_name
            await _rename_file_async(str(file), str(file.parent / new_name))
            click.echo(f"✅ Renamed: {raw_filename} → {new_name}")
        else:
            click.echo(f"⏩ Already correct: {raw_filename}")
