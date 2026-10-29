"""Present source files as recognizable definition categories and named entries."""
from pathlib import PurePosixPath

CATEGORIES = (
    ('base', 'Base', 'Shared instructions inherited by every profile.'),
    ('profiles', 'Profiles', 'Primary agent roles, with instructions and configuration kept together.'),
    ('specializations', 'Specializations', 'Focused expertise grouped under its parent profile.'),
    ('skillsets', 'Skillsets', 'Named bundles of skills and MCP requirements.'),
    ('skills', 'Skills', 'Registered skill sources and their dependencies.'),
    ('mcp', 'MCP servers', 'Registered tool servers available to definitions.'),
    ('templates', 'Templates', 'Authoring templates for new definitions.'),
    ('resources', 'Resources', 'Supporting files referenced by definitions and skills.'),
)


def display_name(name):
    return {'php': 'PHP', 'qa': 'QA', 'mcp': 'MCP', 'c': 'C'}.get(name, name.replace('-', ' ').replace('_', ' ').capitalize())


def classify(path):
    parts = PurePosixPath(path).parts
    filename = PurePosixPath(path).name
    stem = PurePosixPath(path).stem
    if filename == 'TEMPLATE.md' and parts[0] == 'definitions':
        name = 'Specialization template' if 'specializations' in parts else 'Definition template'
        return 'templates', path, name, '', 'Template'
    if path.startswith('definitions/base/'):
        role = 'Instructions' if filename.endswith('.md') else 'Configuration'
        return 'base', 'shared', 'Shared base', '', role
    if len(parts) == 3 and parts[:2] == ('definitions', 'profiles'):
        role = 'Instructions' if filename.endswith('.md') else 'Configuration'
        return 'profiles', stem, display_name(stem), '', role
    if len(parts) == 4 and parts[:2] == ('definitions', 'specializations'):
        role = 'Instructions' if filename.endswith('.md') else 'Configuration'
        return 'specializations', f'{parts[2]}/{stem}', display_name(stem), display_name(parts[2]), role
    if len(parts) == 3 and parts[:2] == ('definitions', 'skillsets'):
        return 'skillsets', stem, display_name(stem), '', 'Configuration'
    if len(parts) == 3 and parts[:2] == ('registry', 'skills'):
        return 'skills', stem, display_name(stem), '', 'Registration'
    if len(parts) == 3 and parts[:2] == ('registry', 'mcp'):
        return 'mcp', stem, display_name(stem), '', 'Configuration'
    return 'resources', str(PurePosixPath(path).parent), str(PurePosixPath(path).parent), '', filename


def definition_navigation(paths):
    grouped = {key: {} for key, _, _ in CATEGORIES}
    for path in sorted(paths):
        category, key, name, parent, role = classify(path)
        item = grouped[category].setdefault(key, {'name': name, 'parent': parent, 'files': []})
        item['files'].append({'path': path, 'label': role})
    result = []
    for key, label, description in CATEGORIES:
        items = list(grouped[key].values())
        for item in items:
            item['files'].sort(key=lambda file: (file['label'] != 'Instructions', file['path']))
        result.append({'key': key, 'label': label, 'description': description, 'items': items,
                       'count': len(items)})
    return result
