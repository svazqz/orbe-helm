"""Deny-by-default resource predicates independent of transport and persistence."""
from .entities import AccessScope
from ..shared.errors import Forbidden

MAX_GRANT_SECONDS = 900


def has_grant(scope: AccessScope, action: str, resource_id: str, now: int):
    return any(g.principal_id == scope.principal_id and g.action == action
               and g.resource_id == resource_id and not g.revoked
               and 0 < g.expires_at - g.issued_at <= MAX_GRANT_SECONDS
               and g.issued_at <= now < g.expires_at for g in scope.grants)


def require_grant(scope: AccessScope, action: str, resource_id: str, now: int):
    if not has_grant(scope, action, resource_id, now):
        raise Forbidden('Access denied')
