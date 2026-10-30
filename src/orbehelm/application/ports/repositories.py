"""Aggregate repository contracts; implementations must filter before pagination."""
from typing import Protocol
from ...domain.access.entities import AccessScope
from ...domain.knowledge.entities import KUnit


class KnowledgeRepository(Protocol):
    def get_visible(self, unit_id: str, scope: AccessScope, now: int) -> KUnit | None: ...
    def query_visible(self, scope: AccessScope, now: int, query: str, limit: int) -> tuple[KUnit, ...]: ...
    def save(self, item: KUnit, expected_revision: int) -> None: ...
