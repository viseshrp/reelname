import asyncio
from pathlib import Path
import re
from typing import Optional, Tuple

import aiofiles.os  # type: ignore[import-untyped]
import click
from imdb import Cinemagoer
from thefuzz import fuzz

from .constants import BRACKETED_PATTERN, DOT_YEAR_PATTERN


def extract_title_and_year(filename: str) -> Optional[Tuple[str, str]]:
    """
    Extract a human-friendly title and year from the filename.
    Tries bracketed (e.g. 'Name (2023)') then dot-separated (e.g. 'Name.2023.').
    """
    match = BRACKETED_PATTERN.search(filename)
    if not match:
        match = DOT_YEAR_PATTERN.search(filename)
    if not match:
        return None

    raw_title = match.group("title").strip()
    year = match.group("year")
    # Replace dots/underscores with spaces
    clean_title = re.sub(r"[._]+", " ", raw_title)
    return clean_title, year


def fetch_official_title_imdb(title: str, year: str) -> Optional[str]:
    """
    Look up the title on IMDb via Cinemagoer.
    1) Search 'title year' exactly.
    2) If no exact, fallback to pure title + fuzzy match.
    """
    ia = Cinemagoer()
    # 1) Exact query
    results = ia.search_movie(f"{title} {year}")
    for movie in results:
        if movie.get("year") == int(year):
            ia.update(movie)
            title_result = movie.get("title")
            if isinstance(title_result, str):
                return title_result

    # 2) Fuzzy fallback
    results = ia.search_movie(title)
    best, best_score = None, 0
    for movie in results:
        if movie.get("year") == int(year):
            candidate = movie.get("title", "")
            if not isinstance(candidate, str):
                continue
            score = fuzz.token_set_ratio(title, candidate)
            if score > best_score:
                best, best_score = movie, score

    if best and best_score >= 60:
        ia.update(best)
        title_result = best.get("title")
        if isinstance(title_result, str):
            return title_result
    return None


def rebuild_filename(original: str, official: str, year: str) -> str:
    """
    Reconstruct the filename as:
      OfficialTitle (Year) + everything after the first '(Year)' in the original.
    """
    parts = re.split(r"\(\s*" + re.escape(year) + r"\s*\)", original, maxsplit=1)
    suffix = parts[1] if len(parts) > 1 else ""
    return f"{official} ({year}){suffix}"


async def _rename_file_async(old_path: str, new_path: str) -> None:
    await aiofiles.os.rename(old_path, new_path)


async def _process_files(directory: Path) -> None:
    """
    Scan `directory` for new files, extract title+year, find the IMDb official
    title, and rename accordingly.
    """
    for file in directory.iterdir():
        if not file.is_file():
            continue

        raw_name = file.name
        info = extract_title_and_year(raw_name)
        if not info:
            click.echo(f"⏩ Skipping (no title/year): {raw_name!s}")
            continue

        raw_title, year = info
        click.echo(f"🔎 Looking up: {raw_title!s} ({year})")
        official = fetch_official_title_imdb(raw_title, year)
        if not official:
            click.echo(f"❌ No IMDb match for: {raw_title!s} ({year})")
            continue

        new_name = rebuild_filename(raw_name, official, year)
        if new_name != raw_name:
            await _rename_file_async(str(file), str(file.parent / new_name))
            click.echo(f"✅ Renamed: {raw_name!s} → {new_name!s}")
        else:
            click.echo(f"⏩ Already correct: {raw_name!s}")
