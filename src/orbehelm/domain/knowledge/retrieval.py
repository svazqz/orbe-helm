"""Deterministic unit segmentation, access decisions, and hybrid rank fusion."""
import re
from ..shared.errors import OrbeHelmError

ACTIVE_STATES = ('reported', 'accepted')
OUTCOME_TYPES = ('decision', 'architecture', 'feature', 'review', 'test', 'constraint')
EVIDENCE_STATES = ('proposed', 'implemented', 'verified')


def visibility(value):
    if value not in {'private', 'project', 'global'}:
        raise OrbeHelmError('Memory visibility must be private, project or global')
    return value


def may_read(owner, unit_owner, unit_visibility, status):
    return bool(owner and status in ACTIVE_STATES and
                (unit_visibility == 'global' or owner == unit_owner))


def outcome_metadata(kind, evidence, audience=None, evidence_state='proposed'):
    if kind not in OUTCOME_TYPES or evidence_state not in EVIDENCE_STATES:
        raise OrbeHelmError('Use a supported knowledge type and evidence state')
    if (not isinstance(evidence, (list, tuple)) or not 1 <= len(evidence) <= 20
            or any(not isinstance(item, str) or not item.strip() or len(item) > 2048 for item in evidence)):
        raise OrbeHelmError('Knowledge requires 1–20 nonempty artifact/revision evidence references')
    audience = ['*'] if audience is None else audience
    if (not isinstance(audience, (list, tuple)) or not 1 <= len(audience) <= 20
            or any(not isinstance(item, str) or not re.fullmatch(r'\*|[a-z][a-z0-9-]*(?::[a-z][a-z0-9-]*)?', item) for item in audience)):
        raise OrbeHelmError('Knowledge audience must contain profiles, profile:spec entries or *')
    return {'kind': kind, 'evidence': list(evidence), 'audience': sorted(set(audience)),
            'evidence_state': evidence_state}


def instruction_like(content):
    """Conservative quarantine, not a complete semantic instruction detector."""
    return bool(re.search(r'(?im)(ignore (?:all |the )?(?:previous|prior|system)|you (?:must|should|are)|'
                          r'^\s*(?:always|never)\b|^#+\s*(?:agent instructions|profile|workflow|scope and autonomy))', content))


def content_text(value):
    if not isinstance(value, str) or not value.strip() or '\x00' in value or len(value.encode()) > 65536:
        raise OrbeHelmError('Knowledge content must be nonempty text of at most 65536 bytes')
    return value.strip()


def segments(content, size=1800):
    """Keep paragraph boundaries where possible, with bounded deterministic pieces."""
    parts, current = [], ''
    for paragraph in re.split(r'\n\s*\n', content.strip()):
        while len(paragraph) > size:
            if current:
                parts.append(current)
                current = ''
            cut = paragraph.rfind(' ', 0, size + 1)
            cut = cut if cut > size // 2 else size
            parts.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        combined = current + ('\n\n' if current else '') + paragraph
        if len(combined) > size:
            parts.append(current)
            current = paragraph
        else:
            current = combined
    if current:
        parts.append(current)
    return tuple(parts)


def lexical_expression(query):
    words = re.findall(r'\w+', query, flags=re.UNICODE)[:32]
    return ' OR '.join('"' + word.replace('"', '""') + '"' for word in words)


def reciprocal_rank_fusion(*rankings):
    scores = {}
    for ranking in rankings:
        seen = set()
        for item in ranking:
            if item not in seen:
                seen.add(item)
                scores[item] = scores.get(item, 0) + 1 / (60 + len(seen))
    return tuple(sorted(scores, key=lambda item: (-scores[item], item)))
