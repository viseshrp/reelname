from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import aiofiles.os
import click
from rapidfuzz import fuzz
from rapidfuzz.utils import default_process

from .constants import (
    BRACKETED_PATTERN,
    DOT_YEAR_PATTERN,
    INVALID_FILENAME_CHARS,
    MEDIA_EXTENSIONS,
    SAMPLE_PATTERN,
    SPACE_YEAR_PATTERN,
    TMDB_SEARCH_URL,
    URL_PREFIX_PATTERN,
)
from .exceptions import TMDbAuthError, TMDbRequestError


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
    Case and punctuation are ignored, so "THE.DARK.KNIGHT" matches "The Dark Knight".
    """
    return min(
        fuzz.ratio(title, candidate, processor=default_process),
        fuzz.token_sort_ratio(title, candidate, processor=default_process),
        fuzz.partial_token_sort_ratio(title, candidate, processor=default_process),
    )


def search_tmdb(title: str, year: str, api_key: str) -> list[dict[str, Any]]:
    """
    Search TMDb for movies called `title` released in `year`.

    `api_key` may be a v3 API key or a v4 API read access token (a JWT, starting "eyJ").
    Raises TMDbAuthError if TMDb rejects the key, TMDbRequestError for any other failure.
    """
    params = {"query": title, "year": year}
    headers = {"Accept": "application/json"}
    if api_key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        params["api_key"] = api_key

    # S310 guards against file:// and custom schemes; the URL here is a fixed https endpoint.
    request = Request(f"{TMDB_SEARCH_URL}?{urlencode(params)}", headers=headers)  # noqa: S310
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310
            payload = json.load(response)
    except HTTPError as exc:
        if exc.code == 401:
            raise TMDbAuthError from exc
        raise TMDbRequestError(str(exc)) from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise TMDbRequestError(str(exc)) from exc

    results: list[dict[str, Any]] = payload.get("results", [])
    return results


def fetch_info_from_tmdb(title: str, year: str, api_key: str) -> tuple[str | None, str | None]:
    """
    Look up the title on TMDb:
      - Search TMDb for the title and year.
      - Keep candidates released in that year, and fuzzy match their titles.
      - If one matches well, return (official_title, year).
      - Otherwise return (None, None), so the file is left alone.
    """
    best_match: str | None = None
    best_score = 0.0
    for movie in search_tmdb(title, year, api_key):
        candidate = movie.get("title")
        release_year = (movie.get("release_date") or "")[:4]
        if not candidate or release_year != year:
            continue
        score = get_match_score(title, candidate)
        if score > best_score:
            best_score = score
            best_match = candidate
            if score >= 98.0:
                break

    if best_match and best_score >= 80:
        click.echo(f"🔎 Found: {best_match} ({year})")
        return best_match, year

    return None, None


def _sanitize_filename(name: str) -> str:
    """
    Remove any characters that are invalid in filenames on Windows (and many other OSes).
    """
    return INVALID_FILENAME_CHARS.sub("", name).strip()


def rebuild_filename(original: str, title: str, year: str) -> str:
    """
    Given a cleaned filename starting at the title/year, reconstruct it as:
      {title} ({year}){suffix}{extension}

    Always uses parentheses around the year, and strips any leftover
    punctuation or brackets before the suffix. The extension is kept as-is.
    """
    stem, extension = os.path.splitext(original)

    # 1) Find the first occurrence of the year in the name
    idx = stem.find(year)
    if idx == -1:
        # (shouldn't happen if caller extracted title/year correctly)
        file_name = f"{title} ({year})"
    else:
        # 2) Take everything after that year
        suffix = stem[idx + len(year) :]

        # 3) Strip any leading punctuation/brackets/whitespace from the suffix,
        #    replacing it with a single space (if there is any suffix at all).
        suffix_clean = re.sub(r"^[\s._\-()\[\]{}<>]+", " ", suffix)

        # 4) Build the new filename
        file_name = f"{title} ({year}){suffix_clean}"

    return _sanitize_filename(file_name) + extension


async def _rename_file_async(old_path: str, new_path: str) -> None:
    await aiofiles.os.rename(old_path, new_path)


async def _process_files(directory: Path, api_key: str) -> None:
    """
    Scan `directory` for media files, skip samples and ones without title/year,
    skip already-formatted ones, look up TMDb, and rename confirmed matches
    without ever overwriting an existing file.
    """
    # Snapshot the listing first: the renames below change the directory.
    for file in sorted(directory.iterdir()):
        if not file.is_file():
            continue

        raw_filename = file.name
        stem, extension = os.path.splitext(raw_filename)

        if extension.lower() not in MEDIA_EXTENSIONS:
            click.echo(f"⏩ Skipping (not a media file): {raw_filename}")
            continue

        if SAMPLE_PATTERN.search(stem):
            click.echo(f"⏩ Skipping (sample/trailer): {raw_filename}")
            continue

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
        try:
            tmdb_title, tmdb_year = fetch_info_from_tmdb(title, year, api_key)
        except TMDbRequestError as exc:
            click.echo(f"⏩ Skipping ({exc}): {raw_filename}")
            continue

        if not tmdb_title or not tmdb_year:
            click.echo(f"⏩ Skipping (no TMDb match): {raw_filename}")
            continue

        # 3) rebuild_filename expects the *cleaned* substring:
        #    we re-slice from the first occurrence of the year
        #    so that rebuild_filename sees “Title(…)suffix”
        start = raw_filename.find(year)
        cleaned = raw_filename[start:]

        new_name = rebuild_filename(cleaned, tmdb_title, tmdb_year)
        if new_name == raw_filename:
            click.echo(f"⏩ Already correct: {raw_filename}")
            continue

        # 4) never overwrite another file (a case-only rename resolves to the same file)
        target = file.parent / new_name
        if target.exists() and not os.path.samefile(file, target):
            click.echo(f"⏩ Skipping (would overwrite {new_name}): {raw_filename}")
            continue

        # rename the *original* file to the cleaned new_name
        await _rename_file_async(str(file), str(target))
        click.echo(f"✅ Renamed: {raw_filename} → {new_name}")
