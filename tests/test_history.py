from pathlib import Path

from click.testing import CliRunner

from reelname.cli import main
from reelname.history import history_path


def names(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


def rename(directory: Path, *options: str) -> str:
    result = CliRunner().invoke(main, [*options, str(directory)])
    assert result.exit_code == 0, result.output
    return result.output


def test_undo_restores_the_last_run(tmp_path: Path) -> None:
    (tmp_path / "Inception.2010.1080p.mkv").write_text("video")
    (tmp_path / "Inception.2010.1080p.en.srt").write_text("subs")
    rename(tmp_path)
    assert names(tmp_path) == ["Inception (2010) 1080p.en.srt", "Inception (2010) 1080p.mkv"]

    output = rename(tmp_path, "--undo")

    assert names(tmp_path) == ["Inception.2010.1080p.en.srt", "Inception.2010.1080p.mkv"]
    assert "↩️ Restored: Inception (2010) 1080p.mkv → Inception.2010.1080p.mkv" in output


def test_undo_goes_back_one_run_at_a_time(tmp_path: Path) -> None:
    (tmp_path / "Inception.2010.mkv").write_bytes(b"")
    rename(tmp_path)
    (tmp_path / "Interstellar.2014.mkv").write_bytes(b"")
    rename(tmp_path)

    rename(tmp_path, "--undo")
    assert names(tmp_path) == ["Inception (2010).mkv", "Interstellar.2014.mkv"]

    rename(tmp_path, "--undo")
    assert names(tmp_path) == ["Inception.2010.mkv", "Interstellar.2014.mkv"]

    assert "Nothing to undo" in rename(tmp_path, "--undo")


def test_undo_only_touches_its_own_directory(tmp_path: Path) -> None:
    movies, shows = tmp_path / "movies", tmp_path / "shows"
    movies.mkdir()
    shows.mkdir()
    (movies / "Inception.2010.mkv").write_bytes(b"")
    (shows / "The.Studio.2025.S01E07.mkv").write_bytes(b"")
    rename(movies)
    rename(shows)

    rename(movies, "--undo")

    assert names(movies) == ["Inception.2010.mkv"]
    assert names(shows) == ["The Studio (2025) S01E07.mkv"]


def test_undo_never_overwrites(tmp_path: Path) -> None:
    (tmp_path / "Inception.2010.mkv").write_text("renamed")
    rename(tmp_path)
    (tmp_path / "Inception.2010.mkv").write_text("a new file with the old name")

    output = rename(tmp_path, "--undo")

    assert (tmp_path / "Inception.2010.mkv").read_text() == "a new file with the old name"
    assert (tmp_path / "Inception (2010).mkv").read_text() == "renamed"
    assert "would overwrite Inception.2010.mkv" in output


def test_undo_dry_run_changes_nothing(tmp_path: Path) -> None:
    (tmp_path / "Inception.2010.mkv").write_bytes(b"")
    rename(tmp_path)

    output = rename(tmp_path, "--undo", "--dry-run")

    assert names(tmp_path) == ["Inception (2010).mkv"]
    assert "📝 Would restore: Inception (2010).mkv → Inception.2010.mkv" in output
    # the run is still there to undo for real
    rename(tmp_path, "--undo")
    assert names(tmp_path) == ["Inception.2010.mkv"]


def test_dry_run_keeps_no_history(tmp_path: Path) -> None:
    (tmp_path / "Inception.2010.mkv").write_bytes(b"")

    rename(tmp_path, "--dry-run")

    assert not history_path().exists()


def test_undo_hardlink_removes_only_the_link(tmp_path: Path) -> None:
    original = tmp_path / "Inception.2010.mkv"
    original.write_text("video")
    rename(tmp_path, "--hardlink")
    assert names(tmp_path) == ["Inception (2010).mkv", "Inception.2010.mkv"]

    output = rename(tmp_path, "--undo")

    assert names(tmp_path) == ["Inception.2010.mkv"]
    assert original.read_text() == "video"
    assert "Removed link" in output


def test_undo_hardlink_keeps_a_file_that_is_no_longer_the_link(tmp_path: Path) -> None:
    (tmp_path / "Inception.2010.mkv").write_text("video")
    rename(tmp_path, "--hardlink")
    link = tmp_path / "Inception (2010).mkv"
    link.unlink()
    link.write_text("a different file now")

    output = rename(tmp_path, "--undo")

    assert link.read_text() == "a different file now"
    assert "no longer a link" in output


def test_undo_brings_files_back_from_output(tmp_path: Path) -> None:
    downloads, library = tmp_path / "downloads", tmp_path / "library"
    downloads.mkdir()
    library.mkdir()
    (downloads / "Inception.2010.mkv").write_bytes(b"")
    result = CliRunner().invoke(main, ["-o", str(library), str(downloads)])
    assert result.exit_code == 0, result.output

    rename(downloads, "--undo")

    assert names(downloads) == ["Inception.2010.mkv"]
    assert names(library) == []


def test_undo_covers_subfolders_of_a_recursive_run(tmp_path: Path) -> None:
    movies = tmp_path / "movies"
    movies.mkdir()
    (movies / "Inception.2010.mkv").write_bytes(b"")
    rename(tmp_path, "-r")

    rename(tmp_path, "--undo")

    assert names(movies) == ["Inception.2010.mkv"]
