import asyncio
from pathlib import Path

import click
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .utils import _process_files


class FileChangeHandler(FileSystemEventHandler):
    """Trigger _process_files when new files appear."""

    def __init__(self, directory: Path, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self.directory = directory
        self.loop = loop

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            click.echo(f"🔔 Detected new file: {event.src_path!s}")
            asyncio.run_coroutine_threadsafe(_process_files(self.directory), self.loop)


def watch_directory(directory: str) -> None:
    """
    Continuously watch `directory` and perform IMDb-based renaming.
    """
    dir_path = Path(directory)
    loop = asyncio.get_event_loop()
    handler = FileChangeHandler(dir_path, loop)
    observer = Observer()
    observer.schedule(handler, str(dir_path), recursive=False)
    observer.start()
    click.echo(f"👀 Watching: {dir_path!s}")

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        click.echo("👋 Stopping watcher...")
        observer.stop()
    observer.join()


def run_once(directory: str) -> None:
    """
    Perform a single-pass scan of `directory` and rename matching files.
    """
    dir_path = Path(directory)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_process_files(dir_path))
    click.echo("✅ Run-once processing complete.")
