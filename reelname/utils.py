from __future__ import annotations

from pathlib import Path
import re

import aiofiles.os
import click
from imdb import Cinemagoer
from rapidfuzz import fuzz

from .constants import (
    BRACKETED_PATTERN,
    DOT_YEAR_PATTERN,
    INVALID_FILENAME_CHARS,
    SPACE_YEAR_PATTERN,
    URL_PREFIX_PATTERN,
)


def extract_title_and_year(filename: str) -> tuple[str | None, str | None]:
    """
    Extract (title, year) from a filename. Handles:
      - optional site/tracker prefixes (e.g. 'www.site.com - ')
      - bracketed years (e.g. [2023], (2022))
      - dot-year (e.g. Title.2023.)
      - space-year (e.g. Title 2023 ...)
    """
    # Drop a tracker prefix if present
    if m := URL_PREFIX_PATTERN.match(filename):
        filename = filename[m.end() :]  # remove only prefix, not all ' - '

    # Try year-extracting patterns
    for pat in (BRACKETED_PATTERN, DOT_YEAR_PATTERN, SPACE_YEAR_PATTERN):
        if m := pat.search(filename):
            raw_title = m.group("title").strip()
            year = m.group("year")

            # Normalize dot/underscore separators to spaces
            title = re.sub(r"[._]+", " ", raw_title).strip()
            return title, year

    return None, None


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


def fetch_info_from_imdb(title: str, year: str) -> tuple[str, str]:
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
        candidate = movie.get("title")
        if not candidate:
            continue
        score = get_match_score(title, candidate)
        if score > best_score:
            movie_year = movie.get("year")
            if not movie_year:
                ia.update(movie)  # fetch full details for this movie
            if str(movie_year) != year:
                continue
            best_score = score
            best_match = movie
            if score >= 98.0:
                break

    if best_match and best_score >= 80:
        imdb_title = best_match.get("title")
        imdb_year = best_match.get("year")
        if imdb_title and imdb_year:  # return the fixed title and year
            click.echo(f"🔎 Found: {imdb_title} ({imdb_year})")
            return imdb_title, str(imdb_year)

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
        suffix_clean = re.sub(r"^[\s._\-()\[\]{}<>]+", " ", suffix)

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
        title, year = extract_title_and_year(raw_filename)
        if not title or not year:
            click.echo(f"⏩ Skipping (no title/year): {raw_filename}")
            continue

        # 2) skip files already beginning with “Title (Year)”
        formatted_prefix = f"{title} ({year})"
        if raw_filename.startswith(formatted_prefix):
            click.echo(f"⏩ Skipping already formatted: {raw_filename}")
            continue

        click.echo(f"🔎 Looking up: {title} ({year})")
        imdb_title, imdb_year = fetch_info_from_imdb(title, year)

        if not imdb_title or not imdb_year:
            click.echo(f"⏩ Skipping (no IMDb match): {raw_filename}")
            continue

        # 3) rebuild_filename expects the *cleaned* substring:
        #    we re-slice from the first occurrence of the year
        #    so that rebuild_filename sees “Title(…)suffix”
        start = raw_filename.find(year)
        cleaned = raw_filename[start:]

        new_name = rebuild_filename(cleaned, imdb_title, imdb_year)
        if new_name != raw_filename:
            # rename the *original* file to the cleaned new_name
            await _rename_file_async(str(file), str(file.parent / new_name))
            click.echo(f"✅ Renamed: {raw_filename} → {new_name}")
        else:
            click.echo(f"⏩ Already correct: {raw_filename}")
