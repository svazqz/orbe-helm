"""Stable errors shared by domain policies and application boundaries."""

class OrbeHelmError(Exception):
    """An actionable configuration or runtime error."""
    code = 'invalid_request'

class Conflict(OrbeHelmError):
    """An expected revision or source changed; refresh before retrying."""
    code = 'conflict'

class Forbidden(OrbeHelmError):
    """The verified caller lacks access to the requested resource."""
    code = 'forbidden'

class UnsupportedCapability(OrbeHelmError):
    """A required operation cannot be supplied by the selected adapter."""
    code = 'unsupported_capability'

class InvalidState(OrbeHelmError):
    """An operation cannot run in the current lifecycle state."""
    code = 'invalid_state'

class IncompleteCapture(OrbeHelmError):
    """Captured history is incomplete and cannot prove completion."""
    code = 'incomplete_capture'
