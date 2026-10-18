from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from .constants import (
    GENERIC_FOLDER_PATTERN,
    MATCH_SCORE_WITH_YEAR,
    SAMPLE_PATTERN,
    SEASON_FOLDER_PATTERN,
    SEASON_MARKER_PATTERN,
    VIDEO_EXTENSIONS,
)
from .parsing import ParsedName, episode_rest, find_imdb_id, parse_filename, parse_show_folder
from .tmdb import Match, best_score, find_matches, match_imdb_id

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


def _folder_imdb_ids(file: Path) -> list[tuple[str, str]]:
    """IMDb IDs that the file's folder name or .nfo give, with where each came from."""
    found = []
    if not _is_structure_root(file.parent) and (imdb_id := find_imdb_id(file.parent.name)):
        found.append((imdb_id, f"folder {file.parent.name}"))
    for nfo in _nfo_files(file):
        if nfo.stat().st_size <= _MAX_NFO_BYTES:
            text = nfo.read_text(encoding="utf-8", errors="ignore")
            if imdb_id := find_imdb_id(text):
                found.append((imdb_id, nfo.name))
    return found


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
      2. the file name
      3. an IMDb ID in the folder name, or in the file's .nfo
      4. the folder name (for episodes, the show folder above "Season 01")
    A match from the folder (3, 4) must agree with the file name's title and year, if any.
    Returns why the file is skipped when nothing confirms it.
    """
    stem = os.path.splitext(file.name)[0]
    parsed = parse_filename(stem)
    marker_rest = episode_rest(stem)
    is_episode = parsed.is_episode if parsed else marker_rest is not None
    rest = parsed.rest if parsed else marker_rest or ""

    if (imdb_id := find_imdb_id(stem)) and (match := match_imdb_id(imdb_id, is_episode, api_key)):
        return Identified(match, rest, f"IMDb ID {imdb_id}")

    reason = "no title found"
    if parsed:
        matches = find_matches(parsed, api_key)
        if len(matches) == 1:
            return Identified(matches[0], parsed.rest)
        reason = _skip_reason(matches)

    for imdb_id, source in _folder_imdb_ids(file):
        if match := match_imdb_id(imdb_id, is_episode, api_key):
            if not _agrees(parsed, match):
                return f"{source} says {match.title} ({match.year})"
            return Identified(match, rest, f"IMDb ID in {source}")

    if from_folder := _parse_folder(file, is_episode, parsed is not None):
        folder, folder_path = from_folder
        matches = find_matches(folder, api_key)
        if len(matches) == 1:
            if not _agrees(parsed, matches[0]):
                return f"folder says {matches[0].title} ({matches[0].year})"
            # an obfuscated movie ("abc123.mkv") takes the release info from its folder
            keep = rest if parsed or is_episode else folder.rest
            return Identified(matches[0], keep, f"folder {folder_path.name}")
        if parsed is None:
            reason = _skip_reason(matches)

    return reason
