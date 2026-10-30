"""Pure dependency traversal state; source acquisition stays outside the domain."""
from ..shared.errors import OrbeHelmError
from ..shared.values import identifier


class DependencyWalk:
    def __init__(self):
        self.active = []
        self.completed = set()
        self.ordered = []

    def enter(self, name):
        identifier(name)
        if name in self.active:
            raise OrbeHelmError(f'Cyclic skill dependency involving {name}')
        if name in self.completed:
            return False
        self.active.append(name)
        return True

    def leave(self, name):
        if not self.active or self.active[-1] != name:
            raise OrbeHelmError('Dependency traversal must finish in reverse entry order')
        self.active.pop()
        self.completed.add(name)
        self.ordered.append(name)


def dependency_order(roots, graph):
    """Plan dependency order from supplied values, without discovering any sources."""
    walk = DependencyWalk()
    def visit(name):
        if walk.enter(name):
            if name not in graph:
                raise OrbeHelmError(f'Unknown skill dependency: {name}')
            for dependency in graph[name]:
                visit(dependency)
            walk.leave(name)
    for name in roots:
        visit(name)
    return tuple(walk.ordered)
