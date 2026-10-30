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
    # Historical counters remain readable; they no longer constrain task lifetime.
    if state not in {'developing', 'blocked', 'awaiting_review', 'awaiting_human_approval',
                     'approved_for_qa', 'reviewed', 'complete'}:
        raise Conflict('Task is not ready for submission')
    if live_delegation:
        raise Conflict('Resolve the existing delegation before submitting another candidate')


def require_delegation(profile, state, candidate_id):
    if profile != 'reviewer':
        raise OrbeHelmError('Developers may request reviewer only; QA requires the operator tasks qa command')
    if state not in {'awaiting_review', 'awaiting_human_approval', 'approved_for_qa',
                     'reviewed', 'complete', 'developing', 'blocked'} or candidate_id is None:
        raise Conflict(f'{profile} delegation requires an active submitted candidate')


def assessment_state(results, pending=False, human_approved=False):
    """Review stops at a human gate; QA is a separate operator-requested stage."""
    if pending:
        return 'assessing'
    if any(value == 'blocked' for value in results.values()):
        return 'blocked'
    if any(value in {'changes_requested', 'failed'} for value in results.values()):
        return 'developing'
    if results.get('reviewer') == 'approved':
        if human_approved:
            return 'complete' if results.get('qa') == 'passed' else 'approved_for_qa'
        return 'awaiting_human_approval'
    return 'awaiting_review'


def completed_state(result):
    return {'approved': 'awaiting_human_approval', 'changes_requested': 'developing',
            'passed': 'complete', 'failed': 'developing', 'blocked': 'blocked'}[result]


def require_reopen(state, rounds, round_limit, pending):
    if state not in {'blocked', 'complete', 'reviewed', 'awaiting_human_approval', 'approved_for_qa'}:
        raise Conflict('Only blocked, reviewed or completed tasks can be explicitly reopened')
    if pending:
        raise Conflict('A pending delegation must be resolved first')
    if round_limit is not None:
        raise OrbeHelmError('Submission limits are no longer supported; tasks accept unlimited candidates')
