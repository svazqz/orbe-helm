"""Stable work identity, independent of specialization and native provider."""
from ..shared.values import canonical, digest


def workstream_id(project_id, profile, unique_key=None):
    return digest(canonical(['workstream', project_id, profile, unique_key or '']).encode())[:32]


def context_id(workstream, specialization=None):
    return digest(canonical(['context', workstream, specialization or '']).encode())[:32]
