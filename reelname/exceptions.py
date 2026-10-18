from __future__ import annotations


class ReelNameError(Exception):
    """
    Base exception. All other exceptions
    inherit from here.
    """

    detail = "An error occurred."

    def __init__(self, extra_detail: str | None = None) -> None:
        super().__init__()
        self.extra_detail = extra_detail

    def __str__(self) -> str:
        if self.extra_detail:
            return f"{self.detail} :: {self.extra_detail}"
        return self.detail


class TMDbAuthError(ReelNameError):
    """
    TMDb rejected the API key. Fatal: every lookup would fail.
    """

    detail = "TMDb rejected the API key. Check TMDB_API_KEY."


class TMDbRequestError(ReelNameError):
    """
    A TMDb lookup failed for any other reason (network, server error, bad response).
    """

    detail = "TMDb lookup failed."


class TMDbNotFoundError(TMDbRequestError):
    """
    TMDb doesn't have what was asked for (HTTP 404), like an episode it doesn't list.
    """

    detail = "Not found on TMDb."
