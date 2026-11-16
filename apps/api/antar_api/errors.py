"""Which errors may be shown to the client, and with what HTTP status."""

from antar.core.errors import (
    AntarError,
    BackendRequestError,
    BackendUnavailableError,
    BenchmarkBusyError,
    CapabilityNotSupportedError,
    ExperimentNotFoundError,
    InvalidImageError,
    ModelNotDownloadedError,
    ModelNotFoundError,
)

GENERIC_MESSAGE = "The request failed. See the Antar API log for details."

# Errors whose message is written for the user and safe to return verbatim.
STATUS_BY_ERROR: dict[type[AntarError], int] = {
    ModelNotFoundError: 404,
    ExperimentNotFoundError: 404,
    ModelNotDownloadedError: 409,
    BenchmarkBusyError: 409,
    CapabilityNotSupportedError: 422,
    InvalidImageError: 422,
    BackendRequestError: 502,
    BackendUnavailableError: 503,
}


def public_message(exc: AntarError) -> str:
    """The error's own message if it is user-facing; otherwise a generic one.

    Unlisted errors may carry local paths, so their text stays in the server log.
    """
    return str(exc) if type(exc) in STATUS_BY_ERROR else GENERIC_MESSAGE
