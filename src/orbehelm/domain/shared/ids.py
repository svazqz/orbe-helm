"""Distinct identity types; construction never generates or resolves identities."""
from typing import NewType

ProjectId = NewType('ProjectId', str)
OrbeId = NewType('OrbeId', str)
ConversationId = NewType('ConversationId', str)
TaskId = NewType('TaskId', str)
KUnitId = NewType('KUnitId', str)
PrincipalId = NewType('PrincipalId', str)
RevisionId = NewType('RevisionId', str)
InvocationId = NewType('InvocationId', str)
