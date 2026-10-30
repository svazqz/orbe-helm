"""Pure knowledge segmentation, rank fusion, and owner-access invariants."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from orbehelm.domain.knowledge.retrieval import segments, reciprocal_rank_fusion, may_read


class PureMemoryTests(unittest.TestCase):
    def test_segments_are_bounded_and_preserve_knowledge_words(self):
        text = ('one two three ' * 1000) + '\n\nLast paragraph.'
        chunks = segments(text)
        self.assertTrue(all(0 < len(chunk) <= 1800 for chunk in chunks))
        self.assertEqual(' '.join(' '.join(chunks).split()), ' '.join(text.split()))

    def test_fusion_deduplicates_chunks_before_counting_unit_ranks(self):
        self.assertEqual(reciprocal_rank_fusion(['a', 'a', 'b'], ['b', 'c']), ('b', 'a', 'c'))

    def test_access_matrix_keeps_private_units_owner_only(self):
        for state in ['reported', 'accepted', 'invalidated', 'retracted']:
            for mode in ['private', 'global']:
                for actor in ['owner', 'other', None]:
                    self.assertEqual(may_read(actor, 'owner', mode, state),
                                     bool(actor and state in {'reported', 'accepted'} and (mode == 'global' or actor == 'owner')))
