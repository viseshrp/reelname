from __future__ import annotations

import asyncio
from pathlib import Path

import click
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .constants import WATCH_SETTLE_SECONDS
from .exceptions import ReelNameError
from .utils import _process_files


def _size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


class FileChangeHandler(FileSystemEventHandler):
    """
    Rename new files once they settle: after `settle_seconds` with no further
    changes and no change in size, so files still being copied are left alone.
    """

    def __init__(
        self,
        directory: Path,
        api_key: str,
        loop: asyncio.AbstractEventLoop,
        settle_seconds: float = WATCH_SETTLE_SECONDS,
    ) -> None:
        super().__init__()
        self.directory = directory
        self.api_key = api_key
        self.loop = loop
        self.settle_seconds = settle_seconds
        # Only touched on the event loop's thread
        self._sizes: dict[Path, int | None] = {}
        self._timer: asyncio.TimerHandle | None = None
        # Created on first use, inside the running loop (Python 3.9 binds it at creation)
        self._lock: asyncio.Lock | None = None

    # Watchdog calls these on its own thread; hand each path to the event loop.
    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            click.echo(f"🔔 Detected new file: {event.src_path!s}")
            self.loop.call_soon_threadsafe(self._changed, Path(str(event.src_path)))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.loop.call_soon_threadsafe(self._changed, Path(str(event.src_path)))

    def on_moved(self, event: FileSystemEvent) -> None:
        # A file moved in from elsewhere counts as new; reelname's own renames don't.
        src, dest = Path(str(event.src_path)), Path(str(event.dest_path))
        if not event.is_directory and src.parent != dest.parent:
            self.loop.call_soon_threadsafe(self._changed, dest)

    def _changed(self, path: Path) -> None:
        self._sizes[path] = _size(path)
        self._restart_timer()

    def _restart_timer(self) -> None:
        if self._timer:
            self._timer.cancel()
        self._timer = self.loop.call_later(self.settle_seconds, self._settle)

    def _settle(self) -> None:
        still_growing = {path for path, size in self._sizes.items() if _size(path) != size}
        if still_growing:
            for path in still_growing:
                self._sizes[path] = _size(path)
            self._restart_timer()
            return
        self._sizes.clear()
        self._timer = None
        self.loop.create_task(self._rename())

    async def _rename(self) -> None:
        # One pass at a time: a pass awaits each rename, so another could interleave
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            try:
                await _process_files(self.directory, self.api_key)
            except ReelNameError as exc:
                click.echo(f"Error: {exc}")


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


def run_once(directory: str, api_key: str, dry_run: bool = False) -> None:
    """
    Perform a single-pass scan of `directory` and rename matching files.
    """
    asyncio.run(_process_files(Path(directory), api_key, dry_run))
    click.echo("✅ Dry run complete." if dry_run else "✅ Run-once processing complete.")
