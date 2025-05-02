from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("reelname")
except PackageNotFoundError:  # pragma: no cover
    # Fallback for local dev or editable installs
    __version__ = "0.0.0"
