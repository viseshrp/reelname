from __future__ import annotations

import asyncio
from dataclasses import dataclass
import errno
import os
from pathlib import Path
import shutil

import aiofiles.os
import click

from .constants import (
    DISC_FOLDERS,
    MEDIA_EXTENSIONS,
    SAMPLE_PATTERN,
    SIDECAR_EXTENSIONS,
    VIDEO_EXTENSIONS,
)
from .exceptions import TMDbRequestError
from .history import RunLog
from .identify import Identified, identify, identify_disc
from .parsing import (
    air_date,
    build_stem,
    episode_marker,
    episode_numbers,
    fit_stem,
    parse_filename,
    plex_episode_stem,
)
from .tmdb import episode_title

# Bytes compared at the start, middle and end of two files to call them duplicates
_SAMPLE_BYTES = 1 << 20


@dataclass(frozen=True)
class Options:
    """How a pass renames files."""

    dry_run: bool = False
    # Also process every folder below the given one
    recursive: bool = False
    # Put renamed files here instead of next to the originals
    output: Path | None = None
    # Hardlink the new name instead of moving, so the original stays (e.g. for seeding)
    hardlink: bool = False
    # Name episodes Plex style, with their title: "Show (2008) - S01E01 - Pilot"
    episode_titles: bool = False


def _stem(path: Path) -> str:
    return os.path.splitext(path.name)[0]


def _is_sidecar_of(sidecar: Path, video: Path) -> bool:
    """'Movie.en.srt' or 'Movie.nfo' belongs to 'Movie.mkv' ('Movie2.srt' doesn't)."""
    stem = _stem(video)
    name = sidecar.name
    return (
        sidecar.suffix.lower() in SIDECAR_EXTENSIONS
        and len(name) > len(stem)
        and name.lower().startswith(stem.lower())
        and not name[len(stem)].isalnum()
    )


def group_files(files: list[Path]) -> list[tuple[Path, list[Path]]]:
    """
    Pair each video with the sidecar files (subtitles, .nfo) named after it, so they
    are renamed together with one lookup. Every other file stands alone.
    """
    videos = [f for f in files if f.suffix.lower() in VIDEO_EXTENSIONS]
    sidecars: dict[Path, list[Path]] = {video: [] for video in videos}
    standalone: list[Path] = []
    for file in files:
        if file in sidecars:
            continue
        if owners := [video for video in videos if _is_sidecar_of(file, video)]:
            # "Movie.Extended.en.srt" belongs to "Movie.Extended.mkv", not "Movie.mkv"
            sidecars[max(owners, key=lambda video: len(_stem(video)))].append(file)
        else:
            standalone.append(file)
    groups = [(video, sidecars[video]) for video in videos] + [(f, []) for f in standalone]
    return sorted(groups, key=lambda group: group[0].name)


def _is_disc(folder: Path) -> bool:
    """A Blu-ray or DVD folder: it holds BDMV or VIDEO_TS."""
    try:
        return any(c.is_dir() and c.name.lower() in ("bdmv", "video_ts") for c in folder.iterdir())
    except OSError:
        return False


def _looks_identical(a: Path, b: Path) -> bool:
    """
    Two files of the same size with the same bytes at the start, middle and end
    (so whole files up to 3 MiB): a duplicate, without reading all of a big video.
    """
    if not (a.is_file() and b.is_file()) or a.stat().st_size != b.stat().st_size:
        return False
    size = a.stat().st_size
    offsets = {0, max(0, size // 2 - _SAMPLE_BYTES // 2), max(0, size - _SAMPLE_BYTES)}
    with a.open("rb") as fa, b.open("rb") as fb:
        for offset in sorted(offsets):
            fa.seek(offset)
            fb.seek(offset)
            if fa.read(_SAMPLE_BYTES) != fb.read(_SAMPLE_BYTES):
                return False
    return True


def _folders(directory: Path, options: Options) -> list[Path]:
    """
    `directory`, and with `recursive` every folder below it, except hidden ones, the
    output folder, and Blu-ray/DVD folders: their files must keep their names, and
    the disc folder itself is renamed as one item.
    """
    if not options.recursive:
        return [directory]
    output = options.output.resolve() if options.output else None
    folders = [directory]
    for root, dirs, _files in os.walk(directory):
        dirs[:] = sorted(
            d
            for d in dirs
            if not d.startswith(".")
            and d.lower() not in DISC_FOLDERS
            and Path(root, d).resolve() != output
            and not _is_disc(Path(root, d))
        )
        folders += [Path(root, d) for d in dirs]
    return folders


class _Renamer:
    """One pass: remembers the names it took, and logs renames for undo."""

    def __init__(self, api_key: str, options: Options) -> None:
        self.api_key = api_key
        self.options = options
        self.log = None if options.dry_run else RunLog()
        self.taken: set[Path] = set()

    def _is_taken(self, src: Path, dst: Path) -> bool:
        if dst in self.taken:
            return True
        if not dst.exists():
            return False
        # a case-only rename resolves to the same file
        return self.options.hardlink or not os.path.samefile(src, dst)

    async def _place(self, src: Path, dst: Path) -> None:
        if self.options.hardlink:
            await aiofiles.os.link(src, dst)
            return
        try:
            await aiofiles.os.rename(src, dst)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            # another drive: copy, then remove the original
            await asyncio.to_thread(shutil.move, src, dst)

    def _is_formatted(self, name: str) -> bool:
        """
        The name already starts with "Title (Year)". With --episode-titles, an episode
        only counts once it's in Plex style ("Show (2008) - S01E01 - ...").
        """
        parsed = parse_filename(os.path.splitext(name)[0])
        if not (parsed and parsed.year):
            return False
        prefix = f"{parsed.title} ({parsed.year})"
        if self.options.episode_titles and parsed.is_episode:
            return name.startswith(f"{prefix} - ")
        return name.startswith(prefix)

    def _plex_stem(self, result: Identified) -> str:
        """An episode's Plex style name, with the episode titles TMDb lists."""
        match = result.match
        titles: list[str] = []
        if numbers := episode_numbers(result.rest):
            season, episodes = numbers
            if match.tmdb_id is not None:
                for episode in episodes:
                    if title := episode_title(match.tmdb_id, season, episode, self.api_key):
                        titles.append(title)
            return plex_episode_stem(
                match.title, match.year, episode_marker(season, episodes), titles
            )
        if aired := air_date(result.rest):
            return plex_episode_stem(match.title, match.year, aired, titles)
        return build_stem(match.title, match.year, result.rest)

    def _new_stem(self, file: Path, stem: str) -> str | None:
        """The new name for `file` (without extension), or None to skip it."""
        # skip files already beginning with “Title (Year)”, unless they move elsewhere
        if self._is_formatted(file.name):
            if self.options.output or self.options.hardlink:
                return stem
            click.echo(f"⏩ Skipping already formatted: {file.name}")
            return None

        parsed = parse_filename(stem)
        label = (
            (f"{parsed.title} ({parsed.year})" if parsed.year else parsed.title) if parsed else stem
        )
        click.echo(f"🔎 Looking up: {label}")
        try:
            result = identify(file, self.api_key)
            if isinstance(result, str):
                click.echo(f"⏩ Skipping ({result}): {file.name}")
                return None
            via = f" via {result.via}" if result.via else ""
            click.echo(f"🔎 Found: {result.match.title} ({result.match.year}){via}")
            if self.options.episode_titles and result.is_episode:
                return self._plex_stem(result)
        except TMDbRequestError as exc:
            click.echo(f"⏩ Skipping ({exc}): {file.name}")
            return None
        return build_stem(result.match.title, result.match.year, result.rest)

    def _blocked(self, plan: list[tuple[Path, Path]]) -> str | None:
        """Why the plan can't go ahead: a new name is taken (maybe by the same file)."""
        for src, dst in plan:
            if self._is_taken(src, dst):
                if _looks_identical(src, dst):
                    return f"duplicate of {dst.name}"
                return f"would overwrite {dst.name}"
        return None

    async def process(self, file: Path, sidecars: list[Path]) -> None:
        stem, extension = os.path.splitext(file.name)

        if extension.lower() not in MEDIA_EXTENSIONS:
            click.echo(f"⏩ Skipping (not a media file): {file.name}")
            return

        if SAMPLE_PATTERN.search(stem):
            click.echo(f"⏩ Skipping (sample/trailer): {file.name}")
            return

        new_stem = self._new_stem(file, stem)
        if new_stem is None:
            return

        # the video and its sidecars move together, or not at all
        suffixes = [extension] + [s.name[len(stem) :] for s in sidecars]
        new_stem = fit_stem(new_stem, max(suffixes, key=lambda s: len(s.encode())))
        folder = self.options.output or file.parent
        plan = [(file, folder / (new_stem + extension))]
        plan += [(s, folder / (new_stem + s.name[len(stem) :])) for s in sidecars]

        if plan[0][1] == file:
            click.echo(f"⏩ Already correct: {file.name}")
            return
        if self.options.hardlink and all(
            dst.exists() and os.path.samefile(src, dst) for src, dst in plan
        ):
            click.echo(f"⏩ Already linked: {file.name}")
            return
        if blocked := self._blocked(plan):
            click.echo(f"⏩ Skipping ({blocked}): {file.name}")
            return

        action, done = ("link", "🔗 Linked") if self.options.hardlink else ("rename", "✅ Renamed")
        for src, dst in plan:
            self.taken.add(dst)
            shown = dst.name if dst.parent == src.parent else str(dst)
            if self.options.dry_run:
                click.echo(f"📝 Would {action}: {src.name} → {shown}")
                continue
            try:
                await self._place(src, dst)
            except OSError as exc:
                click.echo(f"⚠️ Couldn't {action} {src.name}: {exc.strerror or exc}")
                return
            if self.log:
                self.log.record(src, dst, "hardlink" if self.options.hardlink else "move")
            click.echo(f"{done}: {src.name} → {shown}")

    async def process_disc(self, folder: Path) -> None:
        """Rename a whole Blu-ray or DVD folder: "Heat.1995.BluRay" -> "Heat (1995) BluRay"."""
        if self.options.hardlink:
            click.echo(f"⏩ Skipping (a folder can't be hardlinked): {folder.name}")
            return
        if self._is_formatted(folder.name):
            if not self.options.output:
                click.echo(f"⏩ Skipping already formatted: {folder.name}")
                return
            new_name = folder.name
        else:
            click.echo(f"🔎 Looking up disc: {folder.name}")
            try:
                result = identify_disc(folder, self.api_key)
            except TMDbRequestError as exc:
                click.echo(f"⏩ Skipping ({exc}): {folder.name}")
                return
            if isinstance(result, str):
                click.echo(f"⏩ Skipping ({result}): {folder.name}")
                return
            via = f" via {result.via}" if result.via else ""
            click.echo(f"🔎 Found: {result.match.title} ({result.match.year}){via}")
            new_name = fit_stem(build_stem(result.match.title, result.match.year, result.rest), "")

        target = (self.options.output or folder.parent) / new_name
        if target == folder:
            click.echo(f"⏩ Already correct: {folder.name}")
            return
        if blocked := self._blocked([(folder, target)]):
            click.echo(f"⏩ Skipping ({blocked}): {folder.name}")
            return

        self.taken.add(target)
        shown = target.name if target.parent == folder.parent else str(target)
        if self.options.dry_run:
            click.echo(f"📝 Would rename: {folder.name} → {shown}")
            return
        try:
            await self._place(folder, target)
        except OSError as exc:
            click.echo(f"⚠️ Couldn't rename {folder.name}: {exc.strerror or exc}")
            return
        if self.log:
            self.log.record(folder, target, "move")
        click.echo(f"✅ Renamed: {folder.name} → {shown}")


async def _process_files(directory: Path, api_key: str, options: Options | None = None) -> None:
    """
    Rename each media file in `directory` (and below, with `recursive`), with its
    sidecars, to "Title (Year) rest" once TMDb confirms what it is, and each
    Blu-ray/DVD folder the same way. Never overwrites anything. With `dry_run`,
    only print what would happen.
    """
    renamer = _Renamer(api_key, options or Options())
    for folder in _folders(directory, renamer.options):
        # Snapshot the listing first: the renames below change the folder.
        entries = sorted(folder.iterdir())
        for file, sidecars in group_files([path for path in entries if path.is_file()]):
            await renamer.process(file, sidecars)
        # Blu-ray and DVD folders are renamed whole
        for disc in entries:
            if disc.is_dir() and not disc.name.startswith(".") and _is_disc(disc):
                await renamer.process_disc(disc)
