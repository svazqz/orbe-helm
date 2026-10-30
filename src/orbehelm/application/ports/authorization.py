"""The application verifies opaque bindings instead of trusting caller claims."""
from typing import Protocol
from ..context import RequestContext


class AuthorizationPort(Protocol):
    def verify(self, binding: str) -> RequestContext: ...
