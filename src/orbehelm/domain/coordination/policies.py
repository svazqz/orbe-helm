"""Pure workflow decisions shared by persistent and in-memory use cases."""
import re
from ..shared.errors import Conflict, OrbeHelmError
from ..shared.values import canonical, digest

MAX_TEXT = 65536
RESULTS = {'reviewer': frozenset({'approved', 'changes_requested', 'blocked'}),
           'qa': frozenset({'passed', 'failed', 'blocked'})}


def execution_access(profile, managed=False):
    """Execution approval policy is independent of the actor's workflow authority."""
    return 'full-access'


def text_value(value, label, limit=MAX_TEXT):
    if not isinstance(value, str) or not value.strip() or len(value.encode()) > limit or '\x00' in value:
        raise OrbeHelmError(f'{label} must be nonempty text of at most {limit} bytes')
    return value


def unique_key(value):
    text_value(value, 'Unique key', 128)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', value) or any(part in {'', '.', '..'} for part in value.split('/')):
        raise OrbeHelmError('Unique key must use letters, numbers, dots, hyphens, underscores, or nonempty path segments')
    return value


def stable_id(*parts):
    return digest(canonical(parts).encode())[:32]


def require_version(current, expected):
    if type(expected) is not int or current != expected:
        raise Conflict('Task changed; read its current context before retrying')


def require_developer(actor_id, profile, parent_id, owner_id):
    if profile != 'developer' or parent_id is not None or owner_id != actor_id:
        raise OrbeHelmError('Only a root developer orbe can control this task workflow')


def require_submission(state, rounds, max_rounds, live_delegation):
    if state not in {'developing', 'blocked'} or rounds >= max_rounds:
        raise Conflict('Task is not ready for submission or has reached its round limit')
    if live_delegation:
        raise Conflict('Resolve the existing delegation before submitting another candidate')


def require_delegation(profile, state, candidate_id):
    if profile not in RESULTS:
        raise OrbeHelmError('Only reviewer and QA child profiles are supported')
    if state not in {'awaiting_review', 'reviewing', 'testing', 'reviewed', 'assessing'} or candidate_id is None:
        raise Conflict(f'{profile} delegation requires an active submitted candidate')


def assessment_state(results, pending=False):
    """Only independent passing gates for the same candidate complete a task."""
    if pending:
        return 'assessing'
    if any(value == 'blocked' for value in results.values()):
        return 'blocked'
    if any(value in {'changes_requested', 'failed'} for value in results.values()):
        return 'developing'
    if results.get('reviewer') == 'approved' and results.get('qa') == 'passed':
        return 'complete'
    return 'reviewed' if results.get('reviewer') == 'approved' else 'awaiting_review'


def completed_state(result):
    return {'approved': 'reviewed', 'changes_requested': 'developing',
            'passed': 'complete', 'failed': 'developing', 'blocked': 'blocked'}[result]


def require_reopen(state, rounds, round_limit, pending):
    if state not in {'blocked', 'complete'}:
        raise Conflict('Only blocked or completed tasks can be explicitly reopened')
    if pending:
        raise Conflict('A pending delegation must be resolved first')
    if round_limit is not None and (type(round_limit) is not int or not rounds < round_limit <= 100):
        raise OrbeHelmError('Round limit must exceed completed submissions and be at most 100')
