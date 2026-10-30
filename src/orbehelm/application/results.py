"""Transport-neutral results; tracebacks and infrastructure objects stay private."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Result:
    ok: bool
    value: object = None
    code: str | None = None
    message: str | None = None
    request_id: str = ''
