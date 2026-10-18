import asyncio
from pathlib import Path

import click
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .utils import _process_files


class FileChangeHandler(FileSystemEventHandler):
    """Trigger _process_files when new files appear."""

    def __init__(self, directory: Path, api_key: str, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self.directory = directory
        self.api_key = api_key
        self.loop = loop

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            click.echo(f"🔔 Detected new file: {event.src_path!s}")
            asyncio.run_coroutine_threadsafe(
                _process_files(self.directory, self.api_key), self.loop
            )


def watch_directory(directory: str, api_key: str) -> None:
    """
    Continuously watch `directory` and perform TMDb-based renaming.
    """
    dir_path = Path(directory)
    # Create the loop explicitly: asyncio.get_event_loop() raises on Python 3.14+
    # when no loop is running.
    loop = asyncio.new_event_loop()
    handler = FileChangeHandler(dir_path, api_key, loop)
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
    loop.close()


def run_once(directory: str, api_key: str) -> None:
    """
    Perform a single-pass scan of `directory` and rename matching files.
    """
    asyncio.run(_process_files(Path(directory), api_key))
    click.echo("✅ Run-once processing complete.")
