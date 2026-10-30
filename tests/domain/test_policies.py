"""Characterization and invariant checks for extracted production policies."""
from dataclasses import replace
import random
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from orbehelm.domain.shared.errors import Conflict, Forbidden, OrbeHelmError
from orbehelm.domain.shared.values import canonical, digest, identifier
from orbehelm.domain.definitions.composition import MARKER, SECTION_TITLES, compose, parse_sections
from orbehelm.domain.definitions.dependencies import dependency_order
from orbehelm.domain.definitions.validation import validate_mcp
from orbehelm.domain.coordination.policies import (
    require_version, require_developer, require_submission, require_delegation,
    completed_state, require_reopen, stable_id, unique_key,
    execution_access,
)
from orbehelm.domain.conversations.policies import policy_digest, session_reason
from orbehelm.domain.access.entities import AccessScope, AccessGrant
from orbehelm.domain.knowledge.entities import KUnit, Visibility, KnowledgeStatus
from orbehelm.domain.knowledge.policies import can_read, set_visibility, public_projection


def document(**bodies):
    return MARKER + '\n# Fixture\n\n' + '\n\n'.join(
        f'## {title} [{bodies.get(title, ("append", ""))[0]}]\n\n{bodies.get(title, ("append", ""))[1]}'
        for title in SECTION_TITLES)


class CompositionTests(unittest.TestCase):
    def test_dependency_order_deduplicates_diamonds_and_rejects_cycles(self):
        self.assertEqual(dependency_order(['a', 'b'], {'a': ['c', 'b'], 'b': ['c'], 'c': []}), ('c', 'b', 'a'))
        for graph in [{'a': ['a']}, {'a': ['b'], 'b': ['a']}]:
            with self.assertRaisesRegex(OrbeHelmError, 'Cyclic skill dependency involving a'):
                dependency_order(['a'], graph)
        with self.assertRaisesRegex(OrbeHelmError, 'Unknown skill dependency'):
            dependency_order(['missing'], {})

    def test_transport_schema_rejects_credentials_and_invalid_environment_maps(self):
        validate_mcp({'type': 'http', 'url': 'https://example.invalid/mcp'}, 'fixture')
        validate_mcp({'type': 'stdio', 'command': 'fixture', 'env': {'TOKEN': 'HOST_TOKEN'}}, 'fixture')
        for config in [{'type': 'http', 'url': 'https://user:password@example.invalid/mcp'},
                       {'type': 'http', 'url': 'https://example.invalid/mcp?token=secret'},
                       {'type': 'stdio', 'command': 'fixture', 'env': {'TOKEN': 'literal secret'}}]:
            with self.assertRaises(OrbeHelmError):
                validate_mcp(config, 'fixture')

    def test_append_override_clear_and_plain_context_are_byte_stable(self):
        layers = [document(**{'Workflow': ('append', 'old'), 'Responsibilities': ('append', 'duty')}),
                  document(**{'Workflow': ('override', 'new'), 'Responsibilities': ('override', '')}),
                  '# Project\n\nplain']
        self.assertEqual(compose([{'path': str(i), 'content': text} for i, text in enumerate(layers)]),
                         '# Agent Instructions\n\n## Workflow\n\nnew\n\n# Project\n\nplain\n')

    def test_legacy_grammar_and_fenced_headings_remain_supported(self):
        text = document(**{'Workflow': ('append', '```md\n## Example\n```')})
        self.assertEqual(parse_sections(text, 'x'), parse_sections(text.replace('orbehelm:', 'agentic:'), 'x'))
        self.assertIn('## Example', compose([{'path': 'x', 'content': text}]))

    def test_invalid_order_is_rejected_before_composition(self):
        with self.assertRaisesRegex(OrbeHelmError, 'sections must appear exactly once'):
            parse_sections(document().replace('## Workflow [append]', ''), 'fixture.md')

    def test_canonical_identity_matches_historical_bytes(self):
        self.assertEqual(canonical({'z': 'é', 'a': [1, True]}), '{"a":[1,true],"z":"é"}')
        self.assertEqual(digest(b'abc'), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
        self.assertEqual(stable_id('task', 'project', 'key'), digest(b'["task","project","key"]')[:32])
        for value in ['../bad', '', 'A', None, 'a_b']:
            with self.assertRaises(OrbeHelmError):
                identifier(value)


class WorkflowTests(unittest.TestCase):
    def test_reviewer_on_demand_and_qa_is_operator_only(self):
        allowed = {'developing', 'blocked', 'awaiting_review', 'reviewed',
                   'awaiting_human_approval', 'approved_for_qa', 'complete'}
        for state in allowed | {'reviewing', 'testing', 'assessing'}:
            if state in allowed:
                require_delegation('reviewer', state, 'candidate')
            else:
                with self.assertRaises(Conflict):
                    require_delegation('reviewer', state, 'candidate')
            for role in ['qa', 'parallel']:
                with self.assertRaises(OrbeHelmError):
                    require_delegation(role, state, 'candidate')
        self.assertEqual(completed_state('approved'), 'awaiting_human_approval')
        self.assertEqual(completed_state('passed'), 'complete')

    def test_owner_and_compare_and_swap_checks(self):
        self.assertEqual(execution_access('reviewer'), 'full-access')
        self.assertEqual(execution_access('qa'), 'full-access')
        self.assertEqual(execution_access('qa', managed=True), 'full-access')
        require_developer('owner', 'developer', None, 'owner')
        for actor, profile, parent in [('other', 'developer', None), ('owner', 'qa', None), ('owner', 'developer', 'parent')]:
            with self.assertRaises(OrbeHelmError):
                require_developer(actor, profile, parent, 'owner')
        for expected in [True, None, -1, 0, '1']:
            with self.assertRaises(Conflict):
                require_version(1, expected)
        require_version(1, 1)

    def test_unlimited_submissions_and_explicit_recovery(self):
        rng = random.Random(4242)
        for _ in range(100):
            limit = rng.randint(1, 100)
            require_submission('developing', limit - 1, limit, False)
            require_submission('developing', limit + 100, limit, False)
        with self.assertRaises(Conflict):
            require_submission('blocked', 0, 3, True)
        require_reopen('complete', 300, None, False)
        with self.assertRaises(OrbeHelmError):
            require_reopen('complete', 3, 3, False)
        for value in ['a//b', '../a', 'a/..', '/a']:
            with self.assertRaises(OrbeHelmError):
                unique_key(value)

    def test_policy_refresh_excludes_materialization_paths(self):
        resolved = {'composed_instructions': 'rules', 'skills': [], 'mcp': {}}
        policy = policy_digest(resolved)
        self.assertEqual(policy, policy_digest({**resolved, 'root': '/different', 'fingerprint': 'other'}))
        previous = {'agent': 'first', 'policy_digest': policy}
        self.assertEqual(session_reason(previous, policy, 'first'), 'unchanged policy')
        self.assertEqual(session_reason(previous, policy, 'second'), 'agent changed')
        self.assertEqual(session_reason(previous, policy, 'first', True), 'explicit fresh conversation')
        self.assertNotEqual(session_reason(previous, policy_digest({**resolved, 'composed_instructions': 'new'}), 'first'), 'unchanged policy')


class KnowledgeAccessTests(unittest.TestCase):
    def setUp(self):
        self.item = KUnit('unit', 1, 'private content', 'author', 'orbe', project_id='p', orbe_id='o',
                          status=KnowledgeStatus.ACCEPTED, evidence_ids=('private-evidence',))
        self.agent = AccessScope('agent', 'agent', project_id='p', orbe_id='o', task_id='t')

    def test_ownership_matrix_denies_cross_project_and_unbound_callers(self):
        for kind, orbe, task in [('project', 'o', None), ('orbe', 'o', None), ('task', 'o', 't')]:
            item = replace(self.item, owner_kind=kind, orbe_id=orbe, task_id=task)
            self.assertTrue(can_read(item, self.agent, 100))
            for scope in [replace(self.agent, project_id='other'), replace(self.agent, project_id=None), replace(self.agent, role='unknown')]:
                self.assertFalse(can_read(item, scope, 100))
        self.assertFalse(can_read(replace(self.item, owner_kind='orbe', orbe_id='other'), self.agent, 100))
        self.assertFalse(can_read(replace(self.item, owner_kind='task', orbe_id='other', task_id='other'), self.agent, 100))

    def test_collective_requires_acceptance_and_retraction_hides_history(self):
        scope = replace(self.agent, project_id='other')
        for status in KnowledgeStatus:
            item = replace(self.item, visibility=Visibility.COLLECTIVE, status=status)
            self.assertEqual(can_read(item, scope, 100), status in {KnowledgeStatus.REPORTED, KnowledgeStatus.ACCEPTED})

    def test_cross_project_grants_expire_revoke_and_bind_exact_resources(self):
        grant = AccessGrant('grant', 'operator', 'knowledge.read', 'unit', 100, 200)
        operator = AccessScope('operator', 'operator', grants=(grant,))
        self.assertTrue(can_read(self.item, operator, 100))
        for now in [99, 200]:
            self.assertFalse(can_read(self.item, operator, now))
        for change in [{'revoked': True}, {'principal_id': 'other'}, {'action': 'knowledge.publish'},
                       {'resource_id': 'other'}, {'expires_at': 1001}]:
            self.assertFalse(can_read(self.item, replace(operator, grants=(replace(grant, **change),)), 100))

    def test_visibility_preserves_identity_owner_and_redacts_private_provenance(self):
        grant = AccessGrant('publish', 'operator', 'knowledge.visibility', 'unit', 100, 200)
        operator = AccessScope('operator', 'operator', project_id='p', orbe_id='o', grants=(grant,))
        published = set_visibility(self.item, operator, 100, 'global')
        self.assertEqual(self.item.visibility, Visibility.PRIVATE)
        self.assertEqual((published.id, published.orbe_id), (self.item.id, self.item.orbe_id))
        self.assertEqual(published.revision, self.item.revision + 1)
        self.assertNotIn('private-evidence', str(public_projection(published)))
        self.assertNotIn('restricted_source_id', public_projection(published))
        with self.assertRaises(Forbidden):
            set_visibility(self.item, self.agent, 100, 'global')
