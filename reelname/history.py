from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any
import uuid

import click


def history_path() -> Path:
    """Where renames are logged: $REELNAME_DATA_DIR, else the user data directory."""
    if custom := os.environ.get("REELNAME_DATA_DIR"):
        return Path(custom) / "history.jsonl"
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "reelname" / "history.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _absolute(path: Path) -> str:
    # Resolve the folder only: the file itself may already be renamed away
    return str(path.parent.resolve() / path.name)


def _append(entry: dict[str, Any]) -> None:
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _read() -> list[dict[str, Any]]:
    path = history_path()
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue  # ignore a line cut short by a crash
    return entries


class RunLog:
    """Logs each rename of one run, as it happens, so the run can be undone."""

    def __init__(self) -> None:
        self.run_id = uuid.uuid4().hex

    def record(self, src: Path, dst: Path) -> None:
        _append({"run": self.run_id, "time": _now(), "from": _absolute(src), "to": _absolute(dst)})


def undo_last_run(directory: Path, dry_run: bool = False) -> None:
    """
    Rename the files of the most recent run in `directory` back, newest first.
    A file is left alone if it's gone or its old name is taken again.
    """
    entries = _read()
    undone = {e["undo"] for e in entries if "undo" in e}
    folder = str(directory.resolve())
    runs = [
        e["run"]
        for e in entries
        if "run" in e and e["run"] not in undone and str(Path(e["to"]).parent) == folder
    ]
    if not runs:
        click.echo(f"Nothing to undo in {directory}")
        return

    run_id = runs[-1]
    for entry in reversed([e for e in entries if e.get("run") == run_id]):
        src, dst = Path(entry["from"]), Path(entry["to"])
        if not dst.exists():
            click.echo(f"⏩ Skipping (no longer there): {dst.name}")
        elif src.exists():
            click.echo(f"⏩ Skipping (would overwrite {src.name}): {dst.name}")
        elif dry_run:
            click.echo(f"📝 Would restore: {dst.name} → {src.name}")
        else:
            os.rename(dst, src)
            click.echo(f"↩️ Restored: {dst.name} → {src.name}")

    if not dry_run:
        _append({"undo": run_id, "time": _now()})
