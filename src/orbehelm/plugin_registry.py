"""Bundled adapter composition; only this boundary imports concrete plugins."""
from .plugins.codex import Adapter as Codex
from .plugins.claude import Adapter as Claude
from .domain.shared.errors import UnsupportedCapability

_ADAPTERS = {'codex': Codex(), 'claude': Claude()}


def agent_adapter(name):
    try:
        return _ADAPTERS[name]
    except KeyError:
        raise UnsupportedCapability(f'{name}: no supported provider plugin') from None
