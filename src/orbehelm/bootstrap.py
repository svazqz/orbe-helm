"""Composition root; concrete integrations never belong in domain or use cases."""


def execute_legacy(operation, root=None, **data):
    """Preserve existing commands while individually extracting typed use cases."""
    from .infrastructure.compatibility.dispatcher import execute
    return execute(operation, root, **data)


def create_application(registry, authorization):
    from .application import Application
    return Application(registry, authorization)


def legacy_storage(root):
    from .infrastructure.compatibility.dispatcher import storage
    return storage(root)
