"""Static import graph; includes function-local imports without importing the app."""
import ast
from pathlib import Path


def import_graph(source):
    source = Path(source)
    files = {'.'.join(p.relative_to(source).with_suffix('').parts).removesuffix('.__init__'): p
             for p in source.rglob('*.py')}
    graph, external = {name: set() for name in files}, {}
    for module, path in files.items():
        package = module if path.name == '__init__.py' else module.rpartition('.')[0]
        imported = []
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = package.split('.')[:len(package.split('.')) - node.level + 1] if node.level else []
                base = '.'.join(prefix + ([node.module] if node.module else []))
                imported.append(base)
                imported.extend(base + '.' + alias.name for alias in node.names)
        external[module] = {name.split('.')[0] for name in imported if name and not name.startswith('orbehelm')}
        for name in imported:
            while name and name not in files:
                name = name.rpartition('.')[0]
            if name and name != module:
                graph[module].add(name)
    return graph, external


def cyclic_edges(graph):
    """Edges participating in any cycle; removing old edges never adds exceptions."""
    def reaches(start, target):
        pending, seen = [start], set()
        while pending:
            current = pending.pop()
            if current == target:
                return True
            if current not in seen:
                seen.add(current)
                pending.extend(graph.get(current, ()))
        return False
    return {(source, target) for source, targets in graph.items() for target in targets if reaches(target, source)}


def boundary_violations(graph):
    allowed = {
        'domain': {'domain'},
        'application': {'application', 'domain'},
        'infrastructure': {'infrastructure', 'application', 'domain'},
        'plugins': {'plugins', 'application', 'domain'},
        'interfaces': {'interfaces', 'application', 'domain'},
        'integrations': {'integrations', 'application', 'domain'},
    }
    result = set()
    for source, targets in graph.items():
        layer = source.split('.')[1] if '.' in source else ''
        if layer not in allowed:
            continue
        for target in targets:
            target_layer = target.split('.')[1] if '.' in target else ''
            if target_layer not in allowed[layer]:
                result.add((source, target))
            if layer == 'plugins' and target_layer == 'plugins' and source.split('.')[2:3] != target.split('.')[2:3]:
                result.add((source, target))
    return result
