"""Historical ORM classifications are projected into independent domain entities."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from orbehelm.infrastructure.persistence import mappers
from orbehelm.domain.definitions.entities import DefinitionKind
from orbehelm.domain.projects.entities import Project


class MapperTests(unittest.TestCase):
    def test_legacy_definition_kinds_include_plural_directories_and_resources(self):
        for stored, expected in [('profiles', DefinitionKind.PROFILE), ('specializations', DefinitionKind.SPECIALIZATION),
                                 ('skillsets', DefinitionKind.SKILLSET), ('skills', DefinitionKind.SKILL),
                                 ('mcp', DefinitionKind.MCP), ('base', DefinitionKind.BASE),
                                 ('TEMPLATE.md', DefinitionKind.RESOURCE)]:
            row = SimpleNamespace(path='fixture', kind=stored)
            self.assertEqual(mappers.definition(row).kind, expected)

    def test_domain_value_is_detached_from_row_mutation(self):
        row = SimpleNamespace(id='p', path='/workspace', name='Project', active_revision='r')
        value = mappers.project(row)
        self.assertIsInstance(value, Project)
        row.active_revision = 'changed'
        self.assertEqual(value.active_revision, 'r')
