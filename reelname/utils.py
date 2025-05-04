import asyncio
from pathlib import Path
import re

import aiofiles.os
import click
from watchdog.events import FileSystemEvent, FileSystemEventHandler

from .constants import URL_PREFIX_PATTERN


def remove_url_prefix(filename: str) -> str:
    """
    Strip any leading domain-like prefix (containing a dot) plus adjacent
    spaces, dots, underscores, or dashes from the filename.
    """
    return re.sub(URL_PREFIX_PATTERN, "", filename, flags=re.IGNORECASE)


async def _rename_file_async(old_path: str, new_path: str) -> None:
    """Asynchronously rename a file from old_path to new_path."""
    await aiofiles.os.rename(old_path, new_path)


async def _process_files(directory: Path) -> None:
    """
    Iterate over files in `directory`, remove URL prefixes, and rename if changed.
    """
    for file in directory.iterdir():
        if file.is_file():
            new_name = remove_url_prefix(file.name)
            if new_name != file.name:
                new_path = file.parent / new_name
                await _rename_file_async(str(file), str(new_path))
                click.echo(f"✅ Renamed: {file.name!s} → {new_name!s}")
            else:
                click.echo(f"⏩ Skipping: {file.name!s}")


class FileChangeHandler(FileSystemEventHandler):
    """Watchdog handler to trigger renaming on file creation."""

    def __init__(self, directory: Path, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self.directory: Path = directory
        self.loop: asyncio.AbstractEventLoop = loop

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            click.echo(f"🔔 Detected new file: {event.src_path!s}")
            asyncio.run_coroutine_threadsafe(_process_files(self.directory), self.loop)
