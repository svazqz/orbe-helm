"""Immutable descriptions of decisions; dispatch belongs to the application."""
from dataclasses import dataclass


@dataclass(frozen=True)
class DomainEvent:
    kind: str
    aggregate_id: str
    revision: int
    attributes: tuple[tuple[str, str], ...] = ()
