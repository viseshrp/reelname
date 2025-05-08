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
    Extract a human-friendly title and year from the filename by:
      1) Finding where any of our year-patterns first occurs.
      2) Dropping the prefix up to that point.
      3) Re-applying the same pattern on the cleaned substring.
    """
    # 1) Locate the first year-pattern in the raw filename
    m = (
        BRACKETED_PATTERN.search(filename)
        or DOT_YEAR_PATTERN.search(filename)
        or SPACE_YEAR_PATTERN.search(filename)
    )
    if not m:
        return None

    # 2) Strip off any junk before the match
    cleaned = filename[m.start() :]

    # 3) Now re-run the same patterns on 'cleaned'
    m2 = (
        BRACKETED_PATTERN.search(cleaned)
        or DOT_YEAR_PATTERN.search(cleaned)
        or SPACE_YEAR_PATTERN.search(cleaned)
    )
    if not m2:
        return None

    # 4) Extract the title & year groups
    raw_title = m2.group("title").strip()
    year = m2.group("year")
    # Normalize dots/underscores to spaces
    title = re.sub(r"[._]+", " ", raw_title)
    return title, year


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
