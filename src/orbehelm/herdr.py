"""Compatibility exports for the optional terminal integration."""
# Module aliases retain existing monkeypatch points during the transition.
from .integrations.herdr import agent_label, display_label, integration_status, os, shutil, subprocess, sys

__all__ = ['agent_label', 'display_label', 'integration_status']
