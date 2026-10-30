"""Portable policy freshness; native conversation mechanics stay in adapters."""
from ..shared.values import canonical, digest

NATIVE_CONTINUITY = 'native continuity; definition refresh is manual'


def policy_digest(resolved):
    return digest(canonical({'schema_version': 1,
        'instructions': resolved.get('composed_instructions', ''),
        'skills': [(item['name'], item['sha256']) for item in resolved.get('skills', [])],
        'mcp': resolved.get('mcp', {})}).encode())


def session_reason(previous, policy, agent, force=False, memory_enabled=True):
    if force:
        return 'explicit fresh conversation'
    if not previous:
        return 'first conversation'
    if previous.get('mode', 'managed') != 'managed':
        return 'conversation interface changed'
    if previous.get('agent') != agent:
        return 'agent changed'
    if not memory_enabled:
        return NATIVE_CONTINUITY
    if previous.get('memory_enabled', True) is False:
        return 'memory enabled; fresh native context'
    if previous.get('policy_digest') != policy:
        return 'effective instructions or dependencies changed'
    return 'unchanged policy'
