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
from .identify import identify
from .parsing import build_stem, fit_stem, parse_filename


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


def _folders(directory: Path, options: Options) -> list[Path]:
    """
    `directory`, and with `recursive` every folder below it, except hidden ones, the
    output folder, and Blu-ray/DVD structures (BDMV, VIDEO_TS), whose files must
    keep their names.
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

    def _new_stem(self, file: Path, stem: str) -> str | None:
        """The new name for `file` (without extension), or None to skip it."""
        parsed = parse_filename(stem)
        # skip files already beginning with “Title (Year)”, unless they move elsewhere
        if parsed and parsed.year and file.name.startswith(f"{parsed.title} ({parsed.year})"):
            if self.options.output or self.options.hardlink:
                return stem
            click.echo(f"⏩ Skipping already formatted: {file.name}")
            return None

        label = (
            (f"{parsed.title} ({parsed.year})" if parsed.year else parsed.title) if parsed else stem
        )
        click.echo(f"🔎 Looking up: {label}")
        try:
            result = identify(file, self.api_key)
        except TMDbRequestError as exc:
            click.echo(f"⏩ Skipping ({exc}): {file.name}")
            return None
        if isinstance(result, str):
            click.echo(f"⏩ Skipping ({result}): {file.name}")
            return None

        via = f" via {result.via}" if result.via else ""
        click.echo(f"🔎 Found: {result.match.title} ({result.match.year}){via}")
        return build_stem(result.match.title, result.match.year, result.rest)

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
        if blocked := next((dst for src, dst in plan if self._is_taken(src, dst)), None):
            click.echo(f"⏩ Skipping (would overwrite {blocked.name}): {file.name}")
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


async def _process_files(directory: Path, api_key: str, options: Options | None = None) -> None:
    """
    Rename each media file in `directory` (and below, with `recursive`), with its
    sidecars, to "Title (Year) rest" once TMDb confirms what it is. Never overwrites
    a file. With `dry_run`, only print what would happen.
    """
    renamer = _Renamer(api_key, options or Options())
    for folder in _folders(directory, renamer.options):
        # Snapshot the listing first: the renames below change the folder.
        files = sorted(path for path in folder.iterdir() if path.is_file())
        for file, sidecars in group_files(files):
            await renamer.process(file, sidecars)
