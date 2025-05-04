import asyncio
from pathlib import Path

import click
from watchdog.observers import Observer

from .utils import FileChangeHandler


def watch_directory(directory: str) -> None:
    """
    Watch `directory` for new files and strip URL-like prefixes from filenames.
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
