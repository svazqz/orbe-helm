"""Herdr display updates never claim lifecycle state or block model launches."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import contextlib
import io

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from orbehelm.herdr import agent_label, display_label


class HerdrTests(unittest.TestCase):
    def test_label_order_and_absent_fields(self):
        self.assertEqual(agent_label('developer', 'APP-123', 'python'), 'developer - APP-123 - python')
        self.assertEqual(agent_label('developer', spec='python'), 'developer - python')
        self.assertEqual(agent_label('reviewer', 'APP-123'), 'reviewer - APP-123')
        self.assertEqual(agent_label('qa'), 'qa')

    def test_display_is_scoped_to_agent_and_cleared_on_failure(self):
        with patch.dict(os.environ, {'HERDR_ENV': '1', 'HERDR_PANE_ID': 'w1:p2'}), \
                patch('orbehelm.herdr.shutil.which', return_value='/fake/herdr'), \
                patch('orbehelm.herdr.subprocess.run') as run:
            run.return_value.returncode = 0
            with self.assertRaisesRegex(RuntimeError, 'child failed'):
                with display_label('claude', 'developer - APP-123 - python'):
                    raise RuntimeError('child failed')
        self.assertEqual(run.call_args_list[0].args[0], ['/fake/herdr', 'pane', 'report-metadata',
            'w1:p2', '--source', 'orbehelm:display',
            '--display-agent', 'developer - APP-123 - python', '--title', 'developer - APP-123 - python'])
        self.assertIn('--clear-display-agent', run.call_args_list[1].args[0])
        self.assertIn('--clear-title', run.call_args_list[1].args[0])

    def test_binary_discovery_uses_owner_binary_without_path(self):
        with patch.dict(os.environ, {'HERDR_ENV': '1', 'HERDR_PANE_ID': 'w1:p2', 'HERDR_BIN_PATH': '/owner/herdr'}), \
                patch('orbehelm.herdr.shutil.which', return_value=None), \
                patch('orbehelm.herdr.subprocess.run') as run:
            run.return_value.returncode = 0
            with display_label('claude', 'developer'):
                pass
            self.assertEqual(run.call_args.args[0][0], '/owner/herdr')

    def test_outside_herdr_and_headless_do_not_report(self):
        for environment, enabled in [({'HERDR_ENV': '', 'HERDR_PANE_ID': ''}, True),
                                      ({'HERDR_ENV': '1', 'HERDR_PANE_ID': 'w1:p2'}, False)]:
            with patch.dict(os.environ, environment), patch('orbehelm.herdr.subprocess.run') as run:
                with display_label('claude', 'qa', enabled=enabled):
                    pass
                run.assert_not_called()

    def test_failed_or_missing_integration_does_not_block_launch(self):
        with patch.dict(os.environ, {'HERDR_ENV': '1', 'HERDR_PANE_ID': 'w1:p2'}), \
                patch('orbehelm.herdr.shutil.which', return_value='/fake/herdr'), \
                contextlib.redirect_stderr(io.StringIO()):
            for failure in (OSError('missing'), subprocess.TimeoutExpired('herdr', 2)):
                with patch('orbehelm.herdr.subprocess.run', side_effect=failure):
                    with display_label('claude', 'qa'):
                        pass


if __name__ == '__main__':
    unittest.main()
