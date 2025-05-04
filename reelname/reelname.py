import asyncio
from pathlib import Path

import click
from watchdog.observers import Observer

from .utils import FileChangeHandler, _process_files


def watch_directory(directory: str) -> None:
    """
    Watch `directory` for new files and strip URL-like prefixes from filenames.
    """
    dir_path: Path = Path(directory)
    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
    handler: FileChangeHandler = FileChangeHandler(dir_path, loop)
    observer: Observer = Observer()
    observer.schedule(handler, str(dir_path), recursive=False)
    observer.start()
    click.echo(f"👀 Watching: {dir_path}")

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        click.echo("👋 Stopping watcher...")
        observer.stop()
    observer.join()
