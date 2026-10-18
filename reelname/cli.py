from __future__ import annotations

import os
from pathlib import Path

import click

from ._version import __version__
from .exceptions import ReelNameError
from .history import undo_last_run
from .reelname import run_once, watch_directory
from .utils import Options

MISSING_API_KEY = "Set the TMDB_API_KEY environment variable to your TMDb API key."
WATCH_EXCLUSIVE = "--watch can't be combined with --dry-run or --undo."
UNDO_EXCLUSIVE = "--undo only combines with --dry-run."


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-v", "--version")
@click.option(
    "-w",
    "--watch",
    is_flag=True,
    default=False,
    help="Continuously watch directory instead of one-time run",
)
@click.option(
    "-r",
    "--recursive",
    is_flag=True,
    default=False,
    help="Also rename files in every folder below the directory",
)
@click.option(
    "-o",
    "--output",
    metavar="<folder>",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Put renamed files in this folder instead of next to the originals",
)
@click.option(
    "--hardlink",
    is_flag=True,
    default=False,
    help="Add the new name as a hardlink and keep the original (e.g. while seeding)",
)
@click.option(
    "--episode-titles",
    is_flag=True,
    default=False,
    help="Name episodes Plex style, with their title: 'Show (2008) - S01E01 - Pilot'",
)
@click.option(
    "-n",
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be renamed without renaming anything",
)
@click.option(
    "--undo",
    is_flag=True,
    default=False,
    help="Undo the last run in the directory (or below it)",
)
@click.argument(
    "directory",
    metavar="<directory>",
    nargs=1,
    required=False,
    type=click.Path(exists=True, file_okay=False),
)
def main(
    directory: str,
    watch: bool,
    recursive: bool,
    output: Path | None,
    hardlink: bool,
    episode_titles: bool,
    dry_run: bool,
    undo: bool,
) -> None:
    """
    Rename movies and TV episodes by correcting their titles via TMDb.

    Needs a TMDb API key or API read access token in the TMDB_API_KEY
    environment variable. Files with no confirmed TMDb match are left alone.

    By default runs once; use -w/--watch to run continuously.

    \b
    Examples:
      reelname /path/to/media
      reelname -n /path/to/media
      reelname -r -o /path/to/library --hardlink /path/to/downloads
      reelname --episode-titles /path/to/shows
      reelname -w /path/to/media
      reelname --undo /path/to/media
    """
    if watch and (dry_run or undo):
        raise click.UsageError(WATCH_EXCLUSIVE)
    if undo and (watch or recursive or output or hardlink or episode_titles):
        raise click.UsageError(UNDO_EXCLUSIVE)
    if not directory:
        directory = "."
    if undo:
        undo_last_run(Path(directory), dry_run)
        return

    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise click.UsageError(MISSING_API_KEY)
    options = Options(
        dry_run=dry_run,
        recursive=recursive,
        output=output,
        hardlink=hardlink,
        episode_titles=episode_titles,
    )
    try:
        if watch:
            watch_directory(directory, api_key, options)
        else:
            run_once(directory, api_key, options)
    except ReelNameError as exc:
        raise click.ClickException(str(exc)) from exc
