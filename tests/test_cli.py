from pathlib import Path

from click.testing import CliRunner
import pytest

from reelname import __version__, cli
from reelname.cli import main
from tests.data import MOVIE_RENAME_CASES, SKIP_CASES


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


@pytest.mark.parametrize("orig, expected", MOVIE_RENAME_CASES)
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
