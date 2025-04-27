"""Console script for reelname."""

import click

from . import __version__ as _version
from .reelname import do_stuff


@click.argument(
    "stuff",
    metavar="<what_you_worked_on>",
    nargs=-1,
    required=False,
    type=click.STRING,
)
@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(_version, "-v", "--version")
def main(stuff: str) -> None:
    """
    A tool to fix media file names

    \b
    Example usages:

    """
    do_stuff(stuff)


if __name__ == "__main__":
    main()  # pragma: no cover
