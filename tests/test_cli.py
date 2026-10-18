from concurrent.futures import ThreadPoolExecutor
import errno
from pathlib import Path

from click.testing import CliRunner
import pytest

from reelname import __version__, cli, tmdb, utils
from reelname.cli import main
from reelname.exceptions import TMDbAuthError, TMDbRequestError
from reelname.reelname import run_once

from .conftest import FakeTMDb
from .data import MOVIE_RENAME_CASES, NON_MEDIA_CASES, SKIP_CASES, TV_RENAME_CASES


def names(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


@pytest.mark.parametrize("options", [["-h"], ["--help"]])
def test_help(options: list[str]) -> None:
    runner = CliRunner()
    result = runner.invoke(cli.main, options)

    assert result.exit_code == 0, f"Help options {options} failed with exit code {result.exit_code}"
    assert result.output.startswith(
        "Usage: "
    ), f"Help output for {options} did not start with 'Usage:'"
    assert "-h, --help" in result.output, f"Help flags missing from output for {options}"


@pytest.mark.parametrize("options", [["-v"], ["--version"]])
def test_version(options: list[str]) -> None:
    runner = CliRunner()
    result = runner.invoke(cli.main, options)

    assert (
        result.exit_code == 0
    ), f"Version options {options} failed with exit code {result.exit_code}"
    assert (
        __version__ in result.output
    ), f"Expected version {__version__} not found in output for {options}"


@pytest.mark.parametrize("orig, expected", MOVIE_RENAME_CASES + TV_RENAME_CASES)
def test_real_run_once_renames(tmp_path: Path, orig: str, expected: str) -> None:
    # create the sample file
    src = tmp_path / orig
    src.write_bytes(b"")

    runner = CliRunner()
    result = runner.invoke(main, [str(tmp_path)])
    assert result.exit_code == 0, result.output

    # original removed, expected exists
    assert not src.exists(), f"Original still exists: {orig}"
    dst = tmp_path / expected
    assert dst.exists(), f"Expected renamed file not found: {expected}"
    assert f"✅ Renamed: {orig} → {expected}" in result.output


@pytest.mark.parametrize("orig", SKIP_CASES)
def test_real_run_once_skips(tmp_path: Path, orig: str) -> None:
    src = tmp_path / orig
    src.write_bytes(b"")

    runner = CliRunner()
    result = runner.invoke(main, [str(tmp_path)])
    assert result.exit_code == 0, result.output

    assert src.exists(), f"File was unexpectedly renamed: {orig}"
    assert "Skipping" in result.output


def test_episodes_are_looked_up_as_tv_shows(tmp_path: Path, fake_tmdb: FakeTMDb) -> None:
    (tmp_path / "The.Studio.2025.S01E07.Casting.mkv").write_bytes(b"")

    CliRunner().invoke(main, [str(tmp_path)])

    assert fake_tmdb.queries == [("tv", "The Studio", "2025")]


def test_colon_in_title_becomes_dash(tmp_path: Path, fake_tmdb: FakeTMDb) -> None:
    fake_tmdb.results["Mission Impossible"] = [
        {"title": "Mission: Impossible", "release_date": "1996-05-22"}
    ]
    (tmp_path / "Mission.Impossible.1996.1080p.mkv").write_bytes(b"")

    result = CliRunner().invoke(main, [str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert names(tmp_path) == ["Mission - Impossible (1996) 1080p.mkv"]


def test_sidecars_follow_their_video(tmp_path: Path, fake_tmdb: FakeTMDb) -> None:
    for name in [
        "Inception.2010.1080p.mkv",
        "Inception.2010.1080p.en.srt",
        "Inception.2010.1080p.en.forced.srt",
        "Inception.2010.1080p.nfo",
        "Inception.2010.1080p.Extended.mkv",
        "Inception.2010.1080p.Extended.de.srt",
    ]:
        (tmp_path / name).write_text(name)

    result = CliRunner().invoke(main, [str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert names(tmp_path) == [
        "Inception (2010) 1080p.Extended.de.srt",
        "Inception (2010) 1080p.Extended.mkv",
        "Inception (2010) 1080p.en.forced.srt",
        "Inception (2010) 1080p.en.srt",
        "Inception (2010) 1080p.mkv",
        "Inception (2010) 1080p.nfo",
    ]
    # each file kept its own content, and the group needed one lookup per video
    assert (tmp_path / "Inception (2010) 1080p.Extended.de.srt").read_text().endswith(".de.srt")
    assert len(fake_tmdb.queries) == 1, "the second video's search is cached"


def test_sidecars_stay_when_video_is_blocked(tmp_path: Path) -> None:
    (tmp_path / "Inception.2010.mkv").write_text("video")
    (tmp_path / "Inception.2010.en.srt").write_text("subs")
    (tmp_path / "Inception (2010).en.srt").write_text("someone else's subs")

    result = CliRunner().invoke(main, [str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert names(tmp_path) == [
        "Inception (2010).en.srt",
        "Inception.2010.en.srt",
        "Inception.2010.mkv",
    ]
    assert "would overwrite Inception (2010).en.srt" in result.output


def test_collision_never_overwrites(tmp_path: Path) -> None:
    # Two releases that clean up to the same name: the second must not replace the first.
    (tmp_path / "Inception.2010.mkv").write_text("first")
    (tmp_path / "Inception [2010].mkv").write_text("second")

    result = CliRunner().invoke(main, [str(tmp_path)])
    assert result.exit_code == 0, result.output

    assert sorted(p.read_text() for p in tmp_path.iterdir()) == ["first", "second"]
    assert (tmp_path / "Inception (2010).mkv").exists()
    assert "would overwrite Inception (2010).mkv" in result.output


@pytest.mark.parametrize("orig", NON_MEDIA_CASES)
def test_non_media_and_samples_untouched(tmp_path: Path, orig: str, fake_tmdb: FakeTMDb) -> None:
    (tmp_path / orig).write_bytes(b"")

    result = CliRunner().invoke(main, [str(tmp_path)])
    assert result.exit_code == 0, result.output

    assert names(tmp_path) == [orig]
    assert "Skipping" in result.output
    assert fake_tmdb.queries == [], "non-media files must not be looked up"


@pytest.mark.parametrize(
    "results",
    [
        [],
        [{"title": "Inception", "release_date": "2011-07-08"}],
        [{"title": "Interstellar", "release_date": "2010-11-07"}],
    ],
    ids=["nothing-found", "wrong-year", "different-title"],
)
def test_no_tmdb_match_leaves_file_alone(
    tmp_path: Path, fake_tmdb: FakeTMDb, results: list[dict[str, str]]
) -> None:
    fake_tmdb.results["Inception"] = results
    src = tmp_path / "Inception.2010.1080p.mkv"
    src.write_bytes(b"")

    result = CliRunner().invoke(main, [str(tmp_path)])
    assert result.exit_code == 0, result.output

    assert names(tmp_path) == [src.name]
    assert "Skipping (no TMDb match)" in result.output


def test_ambiguous_name_without_year_is_left_alone(tmp_path: Path, fake_tmdb: FakeTMDb) -> None:
    fake_tmdb.results["The Lion King"] = [
        {"title": "The Lion King", "release_date": "2019-07-12"},
        {"title": "The Lion King", "release_date": "1994-06-15"},
    ]
    (tmp_path / "The.Lion.King.1080p.mkv").write_bytes(b"")

    result = CliRunner().invoke(main, [str(tmp_path)])

    assert names(tmp_path) == ["The.Lion.King.1080p.mkv"]
    assert "ambiguous: The Lion King (2019), The Lion King (1994)" in result.output


def test_failed_lookup_leaves_file_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: str) -> None:
        raise TMDbRequestError("timeout")

    monkeypatch.setattr(tmdb, "search", fail)
    src = tmp_path / "Inception.2010.1080p.mkv"
    src.write_bytes(b"")

    result = CliRunner().invoke(main, [str(tmp_path)])
    assert result.exit_code == 0, result.output

    assert src.exists()
    assert "TMDb lookup failed" in result.output


def test_rejected_api_key_aborts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*_args: str) -> None:
        raise TMDbAuthError

    monkeypatch.setattr(tmdb, "search", reject)
    (tmp_path / "Inception.2010.mkv").write_bytes(b"")

    result = CliRunner().invoke(main, [str(tmp_path)])

    assert result.exit_code == 1
    assert "TMDb rejected the API key" in result.output


def test_missing_api_key_is_a_usage_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TMDB_API_KEY")

    result = CliRunner().invoke(main, [str(tmp_path)])

    assert result.exit_code == 2
    assert "TMDB_API_KEY" in result.output


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    (tmp_path / "Inception.2010.mkv").write_bytes(b"")
    (tmp_path / "Inception [2010].mkv").write_bytes(b"")

    result = CliRunner().invoke(main, ["--dry-run", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert names(tmp_path) == ["Inception [2010].mkv", "Inception.2010.mkv"]
    assert "📝 Would rename: Inception [2010].mkv → Inception (2010).mkv" in result.output
    # the dry run also predicts the collision the real run would hit
    assert "would overwrite Inception (2010).mkv): Inception.2010.mkv" in result.output


@pytest.mark.parametrize("options", [["-w", "-n"], ["-w", "--undo"]])
def test_watch_excludes_dry_run_and_undo(tmp_path: Path, options: list[str]) -> None:
    result = CliRunner().invoke(main, [*options, str(tmp_path)])

    assert result.exit_code == 2
    assert "--watch can't be combined" in result.output


def test_run_once_without_current_event_loop(tmp_path: Path) -> None:
    # Python 3.14+ has no current event loop by default. A worker thread never has one
    # on any version, so this reproduces the 3.14 crash everywhere.
    (tmp_path / "Inception.2010.mkv").write_bytes(b"")

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(run_once, str(tmp_path), "test-key").result()

    assert (tmp_path / "Inception (2010).mkv").exists()


def touch(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_recursive_renames_below_but_not_inside_discs_or_hidden_folders(tmp_path: Path) -> None:
    touch(tmp_path / "a" / "Inception.2010.mkv")
    touch(tmp_path / ".hidden" / "Interstellar.2014.mkv")
    touch(tmp_path / "Heat.1995.BluRay" / "BDMV" / "STREAM" / "Heat.1995.m2ts")

    result = CliRunner().invoke(main, ["-r", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert names(tmp_path / "a") == ["Inception (2010).mkv"]
    assert names(tmp_path / ".hidden") == ["Interstellar.2014.mkv"]
    assert names(tmp_path / "Heat.1995.BluRay" / "BDMV" / "STREAM") == ["Heat.1995.m2ts"]


def test_without_recursive_subfolders_are_left_alone(tmp_path: Path) -> None:
    touch(tmp_path / "a" / "Inception.2010.mkv")

    CliRunner().invoke(main, [str(tmp_path)])

    assert names(tmp_path / "a") == ["Inception.2010.mkv"]


def test_output_moves_renamed_files_there(tmp_path: Path) -> None:
    downloads, library = tmp_path / "downloads", tmp_path / "library"
    touch(downloads / "Inception.2010.1080p.mkv", "video")
    touch(downloads / "Inception.2010.1080p.en.srt", "subs")
    library.mkdir()

    result = CliRunner().invoke(main, ["-o", str(library), str(downloads)])

    assert result.exit_code == 0, result.output
    assert names(downloads) == []
    assert names(library) == ["Inception (2010) 1080p.en.srt", "Inception (2010) 1080p.mkv"]


def test_output_takes_already_formatted_files_too(tmp_path: Path, fake_tmdb: FakeTMDb) -> None:
    downloads, library = tmp_path / "downloads", tmp_path / "library"
    touch(downloads / "Inception (2010) 1080p.mkv")
    library.mkdir()

    CliRunner().invoke(main, ["-o", str(library), str(downloads)])

    assert names(library) == ["Inception (2010) 1080p.mkv"]
    assert fake_tmdb.queries == [], "an already formatted name needs no lookup"


def test_recursive_output_inside_the_tree_is_not_reprocessed(
    tmp_path: Path, fake_tmdb: FakeTMDb
) -> None:
    touch(tmp_path / "Inception.2010.mkv")
    (tmp_path / "library").mkdir()
    touch(tmp_path / "library" / "Heat.1995.mkv")

    CliRunner().invoke(main, ["-r", "-o", str(tmp_path / "library"), str(tmp_path)])

    assert names(tmp_path / "library") == ["Heat.1995.mkv", "Inception (2010).mkv"]
    assert [q[1] for q in fake_tmdb.queries] == ["Inception"]


def test_hardlink_keeps_the_original(tmp_path: Path) -> None:
    original = touch(tmp_path / "Inception.2010.mkv", "video")

    result = CliRunner().invoke(main, ["--hardlink", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert names(tmp_path) == ["Inception (2010).mkv", "Inception.2010.mkv"]
    assert (tmp_path / "Inception (2010).mkv").samefile(original)
    assert "🔗 Linked: Inception.2010.mkv → Inception (2010).mkv" in result.output

    again = CliRunner().invoke(main, ["--hardlink", str(tmp_path)])
    assert "Already linked: Inception.2010.mkv" in again.output


def test_hardlink_into_output(tmp_path: Path) -> None:
    downloads, library = tmp_path / "downloads", tmp_path / "library"
    original = touch(downloads / "Inception.2010.mkv")
    library.mkdir()

    CliRunner().invoke(main, ["--hardlink", "-o", str(library), str(downloads)])

    assert names(downloads) == ["Inception.2010.mkv"]
    assert (library / "Inception (2010).mkv").samefile(original)


def test_long_names_are_cut_to_fit(tmp_path: Path, fake_tmdb: FakeTMDb) -> None:
    title = "Birdman or The Unexpected Virtue of Ignorance"
    fake_tmdb.results[title] = [
        {"title": "Birdman or (The Unexpected Virtue of Ignorance)", "release_date": "2014-10-17"}
    ]
    # 255 bytes now, and longer once the title gains its brackets and "(2014)"
    head = "Birdman.or.The.Unexpected.Virtue.of.Ignorance.2014.1080p."
    name = head + "x" * (255 - len(head) - len(".mkv")) + ".mkv"
    touch(tmp_path / name)

    result = CliRunner().invoke(main, [str(tmp_path)])

    assert result.exit_code == 0, result.output
    [renamed] = names(tmp_path)
    assert renamed.startswith("Birdman or (The Unexpected Virtue of Ignorance) (2014) 1080p.xxx")
    assert renamed.endswith("x.mkv")
    assert len(renamed.encode()) == 255


def test_a_failed_rename_skips_only_that_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_rename = utils.aiofiles.os.rename

    async def rename(src: Path, dst: Path) -> None:
        if src.name.startswith("Heat"):
            raise PermissionError(13, "Permission denied")
        await real_rename(src, dst)

    monkeypatch.setattr(utils.aiofiles.os, "rename", rename)
    touch(tmp_path / "Heat.1995.mkv")
    touch(tmp_path / "Inception.2010.mkv")

    result = CliRunner().invoke(main, [str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "⚠️ Couldn't rename Heat.1995.mkv: Permission denied" in result.output
    assert names(tmp_path) == ["Heat.1995.mkv", "Inception (2010).mkv"]


@pytest.mark.parametrize("options", [["--undo", "-r"], ["--undo", "--hardlink"]])
def test_undo_takes_only_dry_run(tmp_path: Path, options: list[str]) -> None:
    result = CliRunner().invoke(main, [*options, str(tmp_path)])

    assert result.exit_code == 2
    assert "--undo only combines with --dry-run" in result.output


def test_output_on_another_drive_is_copied_then_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def cross_device(_src: Path, _dst: Path) -> None:
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(utils.aiofiles.os, "rename", cross_device)
    downloads, library = tmp_path / "downloads", tmp_path / "library"
    touch(downloads / "Inception.2010.mkv", "video")
    library.mkdir()

    result = CliRunner().invoke(main, ["-o", str(library), str(downloads)])

    assert result.exit_code == 0, result.output
    assert names(downloads) == []
    assert (library / "Inception (2010).mkv").read_text() == "video"
