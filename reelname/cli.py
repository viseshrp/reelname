import click

from ._version import __version__
from .reelname import run_once, watch_directory


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-v", "--version")
@click.option(
    "-w",
    "--watch",
    is_flag=True,
    default=False,
    help="Continuously watch directory instead of one-time run",
)
@click.argument(
    "directory",
    metavar="<directory>",
    nargs=1,
    required=False,
    type=click.Path(exists=True, file_okay=False),
)
def main(directory: str, watch: bool) -> None:
    """
    Rename media files by correcting their titles via IMDb.

    By default runs once; use -w/--watch to run continuously.

    \b
    Examples:
      reelname /path/to/media
      reelname -w /path/to/media
    """
    if not directory:
        directory = "."
    if watch:
        watch_directory(directory)
    else:
        run_once(directory)
