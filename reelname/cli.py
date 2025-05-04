import click

from ._version import __version__
from .reelname import watch_directory


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-v", "--version")
@click.argument(
    "directory",
    metavar="<directory>",
    nargs=1,
    required=False,
    type=click.Path(exists=True, file_okay=False),
)
def main(directory: str) -> None:
    """
    A tool to watch a directory and clean media filenames by removing URL prefixes.

    \b
    Example usage:
      reelname /mnt/media/downloads
    """
    if not directory:
        directory = "."
    watch_directory(directory)
