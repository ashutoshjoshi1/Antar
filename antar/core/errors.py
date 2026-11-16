"""Antar exception hierarchy."""


class AntarError(Exception):
    """Base class for all errors raised by Antar."""


class BackendUnavailableError(AntarError):
    """A backend could not be reached or returned an unusable response."""


class BackendRequestError(AntarError):
    """The backend was reached but rejected or failed the request."""


class CapabilityNotSupportedError(AntarError):
    """A backend or model was asked to do something it does not support."""


class ModelNotFoundError(AntarError):
    """The backend does not know the requested model."""


class ModelNotDownloadedError(AntarError):
    """The model exists in the backend's catalog but its weights are not present."""


class InvalidImageError(AntarError):
    """An uploaded image is not acceptable (type, size, or content)."""


class ExperimentNotFoundError(AntarError):
    """No experiment or benchmark record exists for the requested id."""


class BenchmarkBusyError(AntarError):
    """A benchmark is already running; they execute one at a time."""
