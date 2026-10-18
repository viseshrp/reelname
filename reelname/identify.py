from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from .constants import (
    BARE_EPISODE_PATTERN,
    GENERIC_FOLDER_PATTERN,
    MATCH_SCORE_WITH_YEAR,
    SAMPLE_PATTERN,
    SEASON_FOLDER_PATTERN,
    SEASON_MARKER_PATTERN,
    VIDEO_EXTENSIONS,
)
from .parsing import ParsedName, episode_rest, find_imdb_id, parse_filename, parse_show_folder
from .tmdb import ImdbMatch, Match, best_score, find_matches, match_imdb_id

# Folders that hold drives: "/Volumes/Media" says nothing about what's on it
_MOUNT_ROOTS = (Path("/Volumes"), Path("/mnt"), Path("/media"))

# .nfo files bigger than this aren't release info
_MAX_NFO_BYTES = 1_000_000


@dataclass(frozen=True)
class Identified:
    """A file's TMDb match, and the release info to keep after "Title (Year)"."""

    match: Match
    rest: str
    # Where the match came from, when not the file name, e.g. "IMDb ID in Movie.nfo"
    via: str = ""
    # The match is a TV show, and `rest` starts with the episode marker
    is_episode: bool = False


def _is_structure_root(folder: Path) -> bool:
    """A folder whose name isn't about its contents: home, drives, "Downloads", "Movies"..."""
    home = Path.home()
    return (
        folder == folder.parent  # file system root
        or folder in (home, home.parent)
        or folder.parent == home
        or folder.parent in _MOUNT_ROOTS
        or folder.parent.parent in _MOUNT_ROOTS
        or bool(GENERIC_FOLDER_PATTERN.match(folder.name))
    )


def _main_videos(folder: Path) -> list[Path]:
    """The videos in `folder`, leaving out samples and trailers."""
    return [
        f
        for f in folder.iterdir()
        if f.is_file()
        and f.suffix.lower() in VIDEO_EXTENSIONS
        and not SAMPLE_PATTERN.search(os.path.splitext(f.name)[0])
    ]


def _nfo_files(file: Path) -> list[Path]:
    """
    The .nfo files that describe `file`: its own ("Movie.nfo" for "Movie.mkv"), or
    any .nfo in its folder when the folder holds just this one video.
    """
    stem = os.path.splitext(file.name)[0].lower()
    nfos = [f for f in file.parent.iterdir() if f.is_file() and f.suffix.lower() == ".nfo"]
    own = [f for f in nfos if f.name.lower().startswith(stem) and not f.name[len(stem)].isalnum()]
    if own:
        return own
    return nfos if _main_videos(file.parent) == [file] else []


def _nfo_imdb_ids(nfos: list[Path]) -> list[tuple[str, str]]:
    """The IMDb ID in each .nfo that names exactly one, with the file it came from."""
    found = []
    for nfo in nfos:
        if nfo.stat().st_size <= _MAX_NFO_BYTES:
            text = nfo.read_text(encoding="utf-8", errors="ignore")
            if imdb_id := find_imdb_id(text):
                found.append((imdb_id, nfo.name))
    return found


def _folder_imdb_ids(file: Path) -> list[tuple[str, str]]:
    """IMDb IDs that the file's folder name or .nfo give, with where each came from."""
    found = []
    if not _is_structure_root(file.parent) and (imdb_id := find_imdb_id(file.parent.name)):
        found.append((imdb_id, f"folder {file.parent.name}"))
    return found + _nfo_imdb_ids(_nfo_files(file))


def _bare_episode(file: Path, stem: str) -> str | None:
    """
    For "Show/Season 2/05 - Pilot.mkv", the name with a proper episode marker:
    "S02E05 - Pilot". Only in a season folder, and only for names without a marker.
    """
    season = SEASON_FOLDER_PATTERN.match(file.parent.name)
    bare = BARE_EPISODE_PATTERN.match(stem)
    if season is None or bare is None or episode_rest(stem) is not None:
        return None
    return f"S{int(season['season']):02d}E{int(bare['episode']):02d}{stem[bare.end():]}"


def _by_imdb_id(hit: ImdbMatch, rest: str, is_episode: bool, via: str) -> Identified:
    """A file matched by IMDb ID. The ID of one episode gives a file without a marker one."""
    if hit.season is not None and hit.episode is not None and not is_episode:
        marker = f"S{hit.season:02d}E{hit.episode:02d}"
        return Identified(hit.match, f"{marker} {rest}".strip(), via, is_episode=True)
    return Identified(hit.match, rest, via, is_episode=is_episode or hit.season is not None)


def _parse_folder(file: Path, is_episode: bool, has_title: bool) -> tuple[ParsedName, Path] | None:
    """
    What the folder says the file is, and which folder said it. For an episode, the
    show folder (above a "Season 01" folder). For a movie, a release folder holding
    just this one video, with a year in its name ("Inception.2010.1080p.BluRay-GRP").
    """
    folder = file.parent
    in_season_folder = is_episode and bool(SEASON_FOLDER_PATTERN.match(folder.name))
    if in_season_folder:
        folder = folder.parent
    if _is_structure_root(folder):
        return None
    if is_episode:
        # With no show name in the file ("S01E01.mkv"), only trust a folder that is
        # clearly a show's: above "Season 01", or named with a season ("Show.S01.720p")
        if not (has_title or in_season_folder or SEASON_MARKER_PATTERN.search(folder.name)):
            return None
        show = parse_show_folder(folder.name)
        return (show, folder) if show else None
    if _main_videos(file.parent) != [file]:
        return None
    parsed = parse_filename(folder.name)
    return (parsed, folder) if parsed and parsed.year and not parsed.is_episode else None


def _agrees(parsed: ParsedName | None, match: Match) -> bool:
    """
    A match from the folder must fit what the file name says, if it says anything:
    the same year, if it has one, and a similar title.
    """
    if parsed is None:
        return True
    if parsed.year and parsed.year != match.year:
        return False
    return best_score(parsed.title, match.names) >= MATCH_SCORE_WITH_YEAR


def _skip_reason(matches: list[Match]) -> str:
    if len(matches) > 1:
        return "ambiguous: " + ", ".join(f"{m.title} ({m.year})" for m in matches)
    return "no TMDb match"


def identify(file: Path, api_key: str) -> Identified | str:
    """
    Work out which movie or show `file` is, trying in turn:
      1. an IMDb ID in the file name
      2. the file name ("Season 2/05.mkv" counts as S02E05)
      3. an IMDb ID in the folder name, or in the file's .nfo
      4. the folder name (for episodes, the show folder above "Season 01")
    A match from the folder (3, 4) must agree with the file name's title and year, if any.
    Returns why the file is skipped when nothing confirms it.
    """
    stem = os.path.splitext(file.name)[0]
    parsed: ParsedName | None
    marker_rest: str | None
    if bare := _bare_episode(file, stem):
        parsed, marker_rest = None, bare
    else:
        parsed, marker_rest = parse_filename(stem), episode_rest(stem)
    is_episode = parsed.is_episode if parsed else marker_rest is not None
    rest = parsed.rest if parsed else marker_rest or ""

    if (imdb_id := find_imdb_id(stem)) and (hit := match_imdb_id(imdb_id, is_episode, api_key)):
        return _by_imdb_id(hit, rest, is_episode, f"IMDb ID {imdb_id}")

    reason = "no title found"
    if parsed:
        matches = find_matches(parsed, api_key)
        if len(matches) == 1:
            return Identified(matches[0], parsed.rest, is_episode=parsed.is_episode)
        reason = _skip_reason(matches)

    for imdb_id, source in _folder_imdb_ids(file):
        if hit := match_imdb_id(imdb_id, is_episode, api_key):
            if not _agrees(parsed, hit.match):
                return f"{source} says {hit.match.title} ({hit.match.year})"
            return _by_imdb_id(hit, rest, is_episode, f"IMDb ID in {source}")

    if from_folder := _parse_folder(file, is_episode, parsed is not None):
        folder, folder_path = from_folder
        matches = find_matches(folder, api_key)
        if len(matches) == 1:
            if not _agrees(parsed, matches[0]):
                return f"folder says {matches[0].title} ({matches[0].year})"
            # an obfuscated movie ("abc123.mkv") takes the release info from its folder
            keep = rest if parsed or is_episode else folder.rest
            return Identified(matches[0], keep, f"folder {folder_path.name}", is_episode)
        if parsed is None:
            reason = _skip_reason(matches)

    return reason


def identify_disc(folder: Path, api_key: str) -> Identified | str:
    """
    Work out which movie a Blu-ray or DVD folder is ("Heat.1995.BluRay-GRP" holding
    BDMV): by an IMDb ID in its name or in an .nfo inside it, then by its name.
    Returns why the folder is skipped when nothing confirms it.
    """
    parsed = parse_filename(folder.name)
    rest = parsed.rest if parsed else ""
    ids = [(imdb_id, f"IMDb ID {imdb_id}")] if (imdb_id := find_imdb_id(folder.name)) else []
    nfos = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".nfo")
    ids += [(found, f"IMDb ID in {nfo}") for found, nfo in _nfo_imdb_ids(nfos)]

    for imdb_id, via in ids:
        if hit := match_imdb_id(imdb_id, False, api_key):
            if not _agrees(parsed, hit.match):
                return f"{via} says {hit.match.title} ({hit.match.year})"
            return Identified(hit.match, rest, via)

    if parsed is None or parsed.is_episode:
        return "no movie title found"
    matches = find_matches(parsed, api_key)
    return Identified(matches[0], rest) if len(matches) == 1 else _skip_reason(matches)
