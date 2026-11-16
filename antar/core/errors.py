"""Antar exception hierarchy."""


class AntarError(Exception):
    """Base class for all errors raised by Antar."""


class BackendUnavailableError(AntarError):
    """A backend could not be reached or returned an unusable response."""


class CapabilityNotSupportedError(AntarError):
    """A backend was asked to do something it does not support (yet)."""


class ExperimentNotFoundError(AntarError):
    """No experiment record exists for the requested id."""
