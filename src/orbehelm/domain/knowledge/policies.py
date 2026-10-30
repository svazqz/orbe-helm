"""Owner-only private knowledge and audited visibility transitions."""
from dataclasses import replace
from .entities import KUnit, KnowledgeStatus, Visibility
from ..access.entities import AccessScope
from ..access.policies import has_grant, require_grant
from ..shared.errors import Forbidden, InvalidState


def can_read(item: KUnit, scope: AccessScope, now: int):
    if scope.role not in {'agent', 'operator'} or not scope.principal_id:
        return False
    if scope.role == 'agent' and not scope.orbe_id:
        return False
    if item.status not in {KnowledgeStatus.REPORTED, KnowledgeStatus.ACCEPTED}:
        return False
    if item.visibility == Visibility.GLOBAL:
        return True
    if item.visibility == Visibility.PROJECT and item.project_id and item.project_id == scope.project_id:
        return True
    if has_grant(scope, 'knowledge.read', item.id, now):
        return True
    return bool(scope.orbe_id and scope.orbe_id == item.orbe_id
                and scope.project_id and scope.project_id == item.project_id)


def public_projection(item: KUnit):
    """A collective DTO cannot reveal private origin references or evidence IDs."""
    return {'id': item.id, 'revision': item.revision, 'content': item.content,
            'visibility': item.visibility.value, 'status': item.status.value}


def set_visibility(item: KUnit, scope: AccessScope, now: int, target: str):
    if scope.role != 'operator' or scope.orbe_id != item.orbe_id or not can_read(item, scope, now):
        raise Forbidden('Access denied')
    require_grant(scope, 'knowledge.visibility', item.id, now)
    try:
        target = Visibility(target)
    except ValueError as error:
        raise InvalidState('Memory visibility must be private or global') from error
    return replace(item, revision=item.revision + 1, visibility=target) if item.visibility != target else item
