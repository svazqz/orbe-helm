"""Common native-agent translation contract; effects are executed by the caller."""
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Mapping
from ...domain.shared.errors import UnsupportedCapability, OrbeHelmError


def validate_access(access):
    if access not in {'read-only', 'workspace-write', 'full-access'}:
        raise OrbeHelmError('Unknown workspace access intent')


class Support(str, Enum):
    FULL = 'full'
    PARTIAL = 'partial'
    UNSUPPORTED = 'unsupported'


@dataclass(frozen=True)
class Capability:
    name: str
    support: Support
    evidence: str
    limitation: str = ''


@dataclass(frozen=True)
class AdapterCapabilities:
    adapter_id: str
    entries: tuple[Capability, ...]

    def require(self, name: str):
        capability = next((item for item in self.entries if item.name == name), None)
        if capability is None or capability.support != Support.FULL:
            raise UnsupportedCapability(f'{self.adapter_id}: capability {name} is not fully supported')


@dataclass(frozen=True)
class LaunchPlan:
    argv: tuple[str, ...]
    stdin: str | None = None


@dataclass(frozen=True)
class RenderedFile:
    path: str
    content: str


@dataclass(frozen=True)
class NormalizedAgentEvent:
    text: str = ''
    native_id: str | None = None
    terminal: bool = False
    failed: bool = False


class AgentAdapter(Protocol):
    id: str
    def describe(self) -> AdapterCapabilities: ...
    def render(self, instructions: str, servers: Mapping, output: str) -> tuple[RenderedFile, ...]: ...
    def command(self, output: str, prompt: str | None = None) -> LaunchPlan: ...
    def stream_command(self, output: str, access: str, prompt: str,
                       native_id: str | None = None, allowed_tools: tuple[str, ...] = ()) -> LaunchPlan: ...
    def decode_event(self, event: Mapping) -> NormalizedAgentEvent: ...
