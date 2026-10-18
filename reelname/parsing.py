from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re

from .constants import (
    BRACKETED_YEAR_PATTERN,
    EARLIEST_YEAR,
    EPISODE_PATTERN,
    GROUP_PREFIX_PATTERN,
    INVALID_FILENAME_CHARS,
    RELEASE_INFO_PATTERN,
    URL_PREFIX_PATTERN,
    YEAR_TOKEN_PATTERN,
)


@dataclass(frozen=True)
class ParsedName:
    """What a file name says about its title, before any lookup."""

    title: str
    year: str | None
    # Everything after the title and year (episode marker, release info), kept as-is
    rest: str
    # The name has an episode marker, so the title is a TV show
    is_episode: bool


def _is_plausible_year(year: str) -> bool:
    return EARLIEST_YEAR <= int(year) <= date.today().year + 1


def _clean_title(raw: str) -> str:
    """
    Turn a raw title like 'The.Dark.Knight.[' into 'The Dark Knight':
    separators become spaces, and trailing dashes or opening brackets go.
    """
    title = re.sub(r"[._\s]+", " ", raw)
    return re.sub(r"[\s\-(\[{<]+$", "", title).strip()


def _strip_prefixes(stem: str) -> str:
    """Drop a tracker prefix ('yts.mx - ') and a release group prefix ('LOL. ')."""
    if m := URL_PREFIX_PATTERN.match(stem):
        stem = stem[m.end() :]
    # Only strip a group prefix when the name ends with the same group, e.g. "...-LOL"
    if (m := GROUP_PREFIX_PATTERN.match(stem)) and re.search(
        rf"-{re.escape(m['group'])}$", stem, re.IGNORECASE
    ):
        stem = stem[m.end() :]
    return stem


def _find_year(text: str) -> re.Match[str] | None:
    """
    Pick the release year in `text`: a bracketed year if there is one, otherwise the
    last plausible year before the release info starts. A year needs a title before
    it, so "2001.A.Space.Odyssey.1968" picks 1968 and "Blade.Runner.2049.2017"
    skips 2049, which hasn't happened yet.
    """

    def usable(m: re.Match[str]) -> bool:
        return _is_plausible_year(m["year"]) and bool(_clean_title(text[: m.start()]))

    if bracketed := [m for m in BRACKETED_YEAR_PATTERN.finditer(text) if usable(m)]:
        return bracketed[0]

    years = [m for m in YEAR_TOKEN_PATTERN.finditer(text) if usable(m)]
    if not years:
        return None
    info = RELEASE_INFO_PATTERN.search(text)
    before_info = [m for m in years if info is None or m.start() < info.start()]
    return before_info[-1] if before_info else years[0]


def parse_filename(stem: str) -> ParsedName | None:
    """
    Read the title, year and the rest from a file name without its extension:
      - TV episodes: the show name before "S01E07" or "1x07", with an optional year
      - movies with a year: the title before the release year
      - movies without a year: the title before the first release info, like "1080p"
    Returns None when there is no title to look up.
    """
    stem = _strip_prefixes(stem)

    if episode := EPISODE_PATTERN.search(stem):
        head = stem[: episode.start()]
        year = _find_year(head)
        if title := _clean_title(head[: year.start()] if year else head):
            return ParsedName(title, year["year"] if year else None, stem[episode.start() :], True)

    if year := _find_year(stem):
        return ParsedName(
            _clean_title(stem[: year.start()]), year["year"], stem[year.end() :], False
        )

    for info in RELEASE_INFO_PATTERN.finditer(stem):
        if title := _clean_title(stem[: info.start()]):
            return ParsedName(title, None, stem[info.start() :], False)

    return None


def format_title(title: str) -> str:
    """
    Make a looked-up title fit a file name without losing its structure:
    "Mission: Impossible" -> "Mission - Impossible", "2:22" -> "2.22".
    """
    title = re.sub(r"(?<=\d):(?=\d)", ".", title)
    return re.sub(r"\s*:\s*", " - ", title)


def build_stem(parsed: ParsedName, title: str, year: str) -> str:
    """
    Build the new name (without extension) as:
      {title} ({year}) {rest}

    Leftover punctuation or brackets before the rest are dropped, and characters
    that are invalid in file names are removed.
    """
    rest = re.sub(r"^[\s._\-()\[\]{}<>]+", "", parsed.rest)
    stem = f"{format_title(title)} ({year})" + (f" {rest}" if rest else "")
    return INVALID_FILENAME_CHARS.sub("", stem).strip()
