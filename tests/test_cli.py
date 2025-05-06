from pathlib import Path

from click.testing import CliRunner
import pytest

from reelname import __version__, cli
from reelname.cli import main


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


@pytest.mark.parametrize(
    "orig, expected",
    [
        # Known films with clear IMDb entries
        (
            "Inception.2010.1080p.BluRay.x264-REF.mkv",
            "Inception (2010) 1080p.BluRay.x264-REF.mkv",
        ),
        (
            "The.Dark.Knight.2008.720p.WEB-DL.DD5.1.H.264-FLAC-TK.mkv",
            "The Dark Knight (2008) 720p.WEB-DL.DD5.1.H.264-FLAC-TK.mkv",
        ),
        (
            "Parasite.2019.1080p.WEB-DL.DD5.1.H.264-ABCD.mkv",
            "Parasite (2019) 1080p.WEB-DL.DD5.1.H.264-ABCD.mkv",
        ),
    ],
)
def test_real_run_once_renames(tmp_path: Path, orig: str, expected: str) -> None:
    # Create the sample file
    src = tmp_path / orig
    src.write_bytes(b"")  # empty placeholder

    runner = CliRunner()
    # Run CLI in one-off mode
    result = runner.invoke(main, [str(tmp_path)])
    assert result.exit_code == 0, result.output

    # Original should be gone, expected file should exist
    assert not src.exists(), f"Original still exists: {orig}"
    dst = tmp_path / expected
    assert dst.exists(), f"Expected renamed file not found: {expected}"
    # Also verify CLI output mentioned the rename
    assert f"✅ Renamed: {orig} → {expected}" in result.output


@pytest.mark.parametrize(
    "orig",
    [
        # Files without a parsable year should be skipped
        "Some.Random.Show.S02E05.HDTV-XYZ.mkv",
        "JustAFileWithNoYear.txt",
    ],
)
def test_real_run_once_skips(tmp_path: Path, orig: str) -> None:
    src = tmp_path / orig
    src.write_bytes(b"")

    runner = CliRunner()
    result = runner.invoke(main, [str(tmp_path)])
    assert result.exit_code == 0, result.output

    # File should remain untouched
    assert src.exists(), f"File was removed or renamed unexpectedly: {orig}"
    # CLI should mention skipping
    assert "Skipping" in result.output
