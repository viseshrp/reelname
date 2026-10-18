from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re

from .constants import (
    AIR_DATE_PATTERN,
    BRACKETED_YEAR_PATTERN,
    EARLIEST_YEAR,
    EPISODE_PATTERN,
    GROUP_PREFIX_PATTERN,
    IMDB_ID_PATTERN,
    INVALID_FILENAME_CHARS,
    MAX_NAME_BYTES,
    RELEASE_INFO_PATTERN,
    TRAILING_SEASON_PATTERN,
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


def _find_episode(stem: str) -> re.Match[str] | None:
    """The episode marker: "S01E07", "1x07", or a daily show's air date ("2024.01.15")."""
    if m := EPISODE_PATTERN.search(stem):
        return m
    for m in AIR_DATE_PATTERN.finditer(stem):
        try:
            aired = date(int(m["year"]), int(m["month"]), int(m["day"]))
        except ValueError:
            continue
        if _is_plausible_year(str(aired.year)):
            return m
    return None


def parse_filename(stem: str) -> ParsedName | None:
    """
    Read the title, year and the rest from a file name without its extension:
      - TV episodes: the show name before "S01E07", "1x07" or an air date,
        with an optional year
      - movies with a year: the title before the release year
      - movies without a year: the title before the first release info, like "1080p"
    Returns None when there is no title to look up.
    """
    stem = _strip_prefixes(stem)

    if episode := _find_episode(stem):
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


def episode_rest(stem: str) -> str | None:
    """
    Everything from the episode marker on, even with no show name before it:
    "S01E07.Pilot" for "S01E07.Pilot". None if the name has no episode marker.
    """
    stem = _strip_prefixes(stem)
    episode = _find_episode(stem)
    return stem[episode.start() :] if episode else None


def parse_show_folder(name: str) -> ParsedName | None:
    """
    Read a show's name, and its year if given, from the folder holding its episodes:
    "Breaking Bad", "The Office (2005)", "The.Office.US.S01.1080p.WEB-DL".
    """
    name = _strip_prefixes(name)
    for info in RELEASE_INFO_PATTERN.finditer(name):
        if _clean_title(name[: info.start()]):
            name = name[: info.start()]
            break
    name = TRAILING_SEASON_PATTERN.sub("", name.rstrip(" ._-"))
    year = _find_year(name)
    title = _clean_title(name[: year.start()] if year else name)
    return ParsedName(title, year["year"] if year else None, "", True) if title else None


def find_imdb_id(text: str) -> str | None:
    """The IMDb ID in `text` ("tt1375666"), if it holds exactly one."""
    ids = set(IMDB_ID_PATTERN.findall(text))
    return ids.pop() if len(ids) == 1 else None


def episode_numbers(rest: str) -> tuple[int, list[int]] | None:
    """
    The season and episode numbers of the marker starting `rest`:
    "S01E05.720p" -> (1, [5]), "S01E01-E03" -> (1, [1, 2, 3]), "S02E05E06" -> (2, [5, 6]).
    """
    marker = EPISODE_PATTERN.match(rest)
    if marker is None:
        return None
    season = int(marker["season"] or marker["x_season"])
    first = int(marker["episode"] or marker["x_episode"])
    more = re.match(r"(?:-?[Ee]\d{1,3})*", rest[marker.end() :])
    tail = [int(n) for n in re.findall(r"\d+", more.group())] if more else []
    if tail and rest[marker.end()] == "-" and tail[-1] > first:
        return season, list(range(first, min(tail[-1], first + 9) + 1))  # a range: E01-E03
    return season, [first, *tail]


def air_date(rest: str) -> str | None:
    """The air date starting `rest` ("2024.01.15.Guest"), as "2024-01-15"."""
    m = _find_episode(rest)
    if m and m.start() == 0 and m.re is AIR_DATE_PATTERN:
        return f"{m['year']}-{m['month']}-{m['day']}"
    return None


def episode_marker(season: int, episodes: list[int]) -> str:
    """The episode marker: "S01E05", or "S01E01-E03" for several episodes."""
    marker = f"S{season:02d}E{episodes[0]:02d}"
    return marker + (f"-E{episodes[-1]:02d}" if len(episodes) > 1 else "")


def plex_episode_stem(show: str, year: str, marker: str, titles: list[str]) -> str:
    """
    An episode's name as Plex and Jellyfin like it:
    "Breaking Bad (2008) - S01E01 - Pilot", "Show (2019) - S01E01-E03 - A & B & C",
    or for a daily show "The Daily Show (1996) - 2024-01-15".
    """
    parts = [f"{format_title(show)} ({year})", marker]
    if titles:
        parts.append(" & ".join(format_title(title) for title in titles))
    return INVALID_FILENAME_CHARS.sub("", " - ".join(parts)).strip()


def format_title(title: str) -> str:
    """
    Make a looked-up title fit a file name without losing its structure:
    "Mission: Impossible" -> "Mission - Impossible", "2:22" -> "2.22",
    "Face/Off" -> "Face Off".
    """
    title = re.sub(r"\s*[/\\]\s*", " ", title)
    title = re.sub(r"(?<=\d):(?=\d)", ".", title)
    return re.sub(r"\s*:\s*", " - ", title)


def build_stem(title: str, year: str, rest: str) -> str:
    """
    Build the new name (without extension) as:
      {title} ({year}) {rest}

    Leftover punctuation or brackets before the rest are dropped, and characters
    that are invalid in file names are removed.
    """
    rest = re.sub(r"^[\s._\-()\[\]{}<>]+", "", rest)
    stem = f"{format_title(title)} ({year})" + (f" {rest}" if rest else "")
    return INVALID_FILENAME_CHARS.sub("", stem).strip()


def fit_stem(stem: str, longest_suffix: str) -> str:
    """
    Shorten `stem` from the end, so that `stem + longest_suffix` fits the 255-byte
    limit file systems put on a name. The release info at the end is what gets cut;
    the suffix (extension) is kept whole.
    """
    while stem and len((stem + longest_suffix).encode()) > MAX_NAME_BYTES:
        stem = stem[:-1]
    return stem.rstrip(" ._-")
