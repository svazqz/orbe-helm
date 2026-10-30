"""Explicit operation schemas and handlers, independent of concrete transports."""
from dataclasses import dataclass
from typing import Callable, Mapping
from .commands import Request
from .context import RequestContext


@dataclass(frozen=True)
class Operation:
    name: str
    handler: Callable[[Request, RequestContext], object]
    required: Mapping[str, type]
    optional: Mapping[str, type]
    effect: str = 'read'


class Registry:
    def __init__(self):
        self._operations = {}

    def register(self, operation: Operation):
        if operation.name in self._operations:
            raise ValueError('Duplicate application operation: ' + operation.name)
        if operation.effect not in {'read', 'write', 'process', 'network'}:
            raise ValueError('Unknown effect class')
        self._operations[operation.name] = operation

    def get(self, name):
        return self._operations.get(name)

    def describe(self):
        return tuple({'name': op.name, 'effect': op.effect,
                      'required': tuple(sorted(op.required)), 'optional': tuple(sorted(op.optional))}
                     for op in sorted(self._operations.values(), key=lambda item: item.name))
