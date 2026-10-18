from __future__ import annotations

import os
from pathlib import Path

import aiofiles.os
import click

from .constants import MEDIA_EXTENSIONS, SAMPLE_PATTERN, SIDECAR_EXTENSIONS, VIDEO_EXTENSIONS
from .exceptions import TMDbRequestError
from .history import RunLog
from .parsing import build_stem, parse_filename
from .tmdb import find_matches


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


class _Renamer:
    """One pass over a directory: remembers the names it took, and logs renames for undo."""

    def __init__(self, api_key: str, dry_run: bool) -> None:
        self.api_key = api_key
        self.dry_run = dry_run
        self.log = None if dry_run else RunLog()
        self.taken: set[Path] = set()

    def _is_taken(self, src: Path, dst: Path) -> bool:
        if dst in self.taken:
            return True
        # a case-only rename resolves to the same file
        return dst.exists() and not os.path.samefile(src, dst)

    async def process(self, file: Path, sidecars: list[Path]) -> None:
        stem, extension = os.path.splitext(file.name)

        if extension.lower() not in MEDIA_EXTENSIONS:
            click.echo(f"⏩ Skipping (not a media file): {file.name}")
            return

        if SAMPLE_PATTERN.search(stem):
            click.echo(f"⏩ Skipping (sample/trailer): {file.name}")
            return

        parsed = parse_filename(stem)
        if parsed is None:
            click.echo(f"⏩ Skipping (no title found): {file.name}")
            return

        # skip files already beginning with “Title (Year)”
        if parsed.year and file.name.startswith(f"{parsed.title} ({parsed.year})"):
            click.echo(f"⏩ Skipping already formatted: {file.name}")
            return

        label = f"{parsed.title} ({parsed.year})" if parsed.year else parsed.title
        click.echo(f"🔎 Looking up: {label}")
        try:
            matches = find_matches(parsed, self.api_key)
        except TMDbRequestError as exc:
            click.echo(f"⏩ Skipping ({exc}): {file.name}")
            return
        if not matches:
            click.echo(f"⏩ Skipping (no TMDb match): {file.name}")
            return
        if len(matches) > 1:
            options = ", ".join(f"{m.title} ({m.year})" for m in matches)
            click.echo(f"⏩ Skipping (ambiguous: {options}): {file.name}")
            return

        match = matches[0]
        click.echo(f"🔎 Found: {match.title} ({match.year})")
        new_stem = build_stem(parsed, match.title, match.year)
        if new_stem + extension == file.name:
            click.echo(f"⏩ Already correct: {file.name}")
            return

        # the video and its sidecars move together, or not at all
        plan = [(file, file.with_name(new_stem + extension))]
        plan += [(s, s.with_name(new_stem + s.name[len(stem) :])) for s in sidecars]
        if blocked := next((dst for src, dst in plan if self._is_taken(src, dst)), None):
            click.echo(f"⏩ Skipping (would overwrite {blocked.name}): {file.name}")
            return

        for src, dst in plan:
            self.taken.add(dst)
            if self.dry_run:
                click.echo(f"📝 Would rename: {src.name} → {dst.name}")
                continue
            await aiofiles.os.rename(src, dst)
            if self.log:
                self.log.record(src, dst)
            click.echo(f"✅ Renamed: {src.name} → {dst.name}")


async def _process_files(directory: Path, api_key: str, dry_run: bool = False) -> None:
    """
    Scan `directory` and rename each media file, with its sidecars, to
    "Title (Year) rest" once TMDb confirms the title. Never overwrites a file.
    With `dry_run`, only print what would be renamed.
    """
    # Snapshot the listing first: the renames below change the directory.
    files = sorted(path for path in directory.iterdir() if path.is_file())
    renamer = _Renamer(api_key, dry_run)
    for file, sidecars in group_files(files):
        await renamer.process(file, sidecars)
