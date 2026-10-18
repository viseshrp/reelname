import asyncio
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileMovedEvent

from reelname.reelname import FileChangeHandler

SETTLE = 0.2


async def wait_for(path: Path, timeout: float = 5.0) -> bool:
    for _ in range(int(timeout / 0.05)):
        if path.exists():
            return True
        await asyncio.sleep(0.05)
    return False


def test_waits_until_changes_stop(tmp_path: Path) -> None:
    async def scenario() -> None:
        handler = FileChangeHandler(tmp_path, "key", asyncio.get_running_loop(), SETTLE)
        movie = tmp_path / "Inception.2010.mkv"
        movie.write_bytes(b"a")
        handler.on_created(FileCreatedEvent(str(movie)))

        # keep writing for longer than the settle time
        for chunk in range(4):
            await asyncio.sleep(SETTLE / 2)
            movie.write_bytes(b"a" * (chunk + 2))
            handler.on_modified(FileModifiedEvent(str(movie)))
            assert movie.exists(), "renamed while still being written"

        assert await wait_for(tmp_path / "Inception (2010).mkv")

    asyncio.run(scenario())


def test_waits_while_size_still_changes(tmp_path: Path) -> None:
    async def scenario() -> None:
        handler = FileChangeHandler(tmp_path, "key", asyncio.get_running_loop(), SETTLE)
        movie = tmp_path / "Inception.2010.mkv"
        movie.write_bytes(b"a")
        handler.on_created(FileCreatedEvent(str(movie)))

        # the file grows without an event (some copiers write without notifying)
        await asyncio.sleep(SETTLE / 2)
        movie.write_bytes(b"ab")
        await asyncio.sleep(SETTLE)
        assert movie.exists(), "renamed while its size was still changing"

        assert await wait_for(tmp_path / "Inception (2010).mkv")

    asyncio.run(scenario())


def test_ignores_own_renames(tmp_path: Path) -> None:
    async def scenario() -> None:
        handler = FileChangeHandler(tmp_path, "key", asyncio.get_running_loop(), SETTLE)
        movie = tmp_path / "Inception.2010.mkv"
        movie.write_bytes(b"")
        renamed = tmp_path / "Inception (2010).mkv"

        # a rename inside the folder (what reelname itself does) doesn't trigger a pass
        handler.on_moved(FileMovedEvent(str(renamed), str(movie)))
        await asyncio.sleep(SETTLE * 3)
        assert movie.exists()

        # a file moved in from another folder does
        handler.on_moved(FileMovedEvent(str(tmp_path.parent / movie.name), str(movie)))
        assert await wait_for(renamed)

    asyncio.run(scenario())


def test_ignores_files_moved_out(tmp_path: Path) -> None:
    async def scenario() -> None:
        handler = FileChangeHandler(tmp_path, "key", asyncio.get_running_loop(), SETTLE)
        outside = tmp_path.parent / f"{tmp_path.name}-elsewhere"
        outside.mkdir()
        moved = outside / "Inception.2010.mkv"
        moved.write_bytes(b"")
        handler.on_moved(FileMovedEvent(str(tmp_path / moved.name), str(moved)))
        await asyncio.sleep(SETTLE * 3)
        assert handler._timer is None, "a file leaving the folder must not trigger a pass"

    asyncio.run(scenario())
