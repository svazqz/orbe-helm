"""Public application API with a backward-compatible checkout entry point."""
from .api import Application
from .commands import Request
from .results import Result


def execute(operation, root=None, **data):
    # The compatibility entry is a composition boundary, not an inward use case.
    from ..bootstrap import execute_legacy
    return execute_legacy(operation, root, **data)


def storage(root):
    """Compatibility storage context for callers awaiting repository extraction."""
    from ..bootstrap import legacy_storage
    return legacy_storage(root)


__all__ = ['Application', 'Request', 'Result', 'execute', 'storage']
