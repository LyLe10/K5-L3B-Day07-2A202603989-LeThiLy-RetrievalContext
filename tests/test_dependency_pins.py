"""Gate A: no HTTP; dependency drift is injected without editing source files."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from scripts import dev_improvement_experiment as runner
from tests.test_improvement_runner import header, initialize


class DependencyPinTests(unittest.TestCase):
    def changed_digest(self, path):
        real_digest = runner.digest
        def injected(candidate):
            return '0'*64 if Path(candidate) == path else real_digest(candidate)
        return injected

    def test_unchanged_dependency_preflight_and_resume_identity_valid(self):
        pin = runner.validate_dependencies()
        for arm in ('E1', 'E2'):
            identity, cases, chunks = runner.design(arm, Path(pin['day6_root']))
            self.assertEqual(len(cases), 17)
            self.assertEqual(len(chunks), 264)
            self.assertEqual(set(identity['code_sha256']), set(runner.CODE_DEPENDENCIES))
            with tempfile.TemporaryDirectory() as directory:
                initialize(directory, identity)
                self.assertEqual(runner.state(directory, identity)['calls'], 0)
                self.assertEqual(runner.ExperimentBudget(directory, identity, verify=MagicMock()).calls, 0)

    def test_every_local_dependency_change_fails_closed(self):
        for name in runner.CODE_DEPENDENCIES:
            with self.subTest(dependency=name), patch.object(runner, 'digest',
                side_effect=self.changed_digest(runner.ROOT/name)):
                with self.assertRaisesRegex(RuntimeError, 'CODE_DEPENDENCY_CHANGED'):
                    runner.validate_dependencies()

    def test_day6_dynamic_dependency_change_fails_without_modifying_day6(self):
        pin = runner.validate_dependencies()
        for name in runner.DAY6_CODE_DEPENDENCIES:
            with self.subTest(dependency=name), patch.object(runner, 'digest',
                side_effect=self.changed_digest(Path(pin['day6_root'])/name)):
                with self.assertRaisesRegex(RuntimeError, 'DAY6_CODE_DEPENDENCY_CHANGED'):
                    runner.validate_dependencies()

    def test_missing_dependency_in_old_identity_never_migrates(self):
        for field in ('code_sha256', 'day6_code_sha256', 'dependency_pin_sha256'):
            h = header()
            h.pop(field)
            with tempfile.TemporaryDirectory() as directory:
                initialize(directory, h)
                with self.assertRaisesRegex(RuntimeError, 'DEPENDENCY_IDENTITY_MISSING'):
                    runner.state(directory, h)
        h = header()
        h['code_sha256'] = dict(h['code_sha256'])
        h['code_sha256'].pop('scripts/milestone5c_pilot.py')
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory, h)
            with self.assertRaisesRegex(RuntimeError, 'DEPENDENCY_IDENTITY_MISSING'):
                runner.state(directory, h)

    def test_incomplete_external_pin_or_loaded_code_mismatch_stops(self):
        pin = deepcopy(runner.read(runner.DEPENDENCY_PIN))
        pin['code_sha256'].pop('scripts/milestone5c_pilot.py')
        with patch.object(runner, 'read', return_value=pin):
            with self.assertRaisesRegex(RuntimeError, 'DEPENDENCY_PIN_INCOMPLETE'):
                runner.validate_dependencies()
        with patch.object(runner, 'LOADED_CODE_HASHES', {}):
            with self.assertRaisesRegex(RuntimeError, 'CODE_DEPENDENCY_CHANGED'):
                runner.validate_dependencies()

    def test_new_run_and_resume_cannot_bypass_validation_before_http(self):
        pin = runner.validate_dependencies()
        for resume in (False, True):
            argv = ['experiment', '--experiment', 'E1', '--mode', 'run',
                '--approve-paid-experiment', '--approved-envelope-usd', '.204',
                '--day6-root', pin['day6_root'], '--output', '/tmp/not-created-gate-a.json']
            if resume: argv.append('--resume')
            with patch.object(sys, 'argv', argv), patch.object(runner, 'digest',
                side_effect=self.changed_digest(runner.ROOT/'scripts/milestone5c_pilot.py')), \
                patch.object(runner, 'verify_key_budget') as key, \
                patch.object(runner, 'check_catalog') as pricing, \
                patch.object(runner, 'build_opener') as http:
                with self.assertRaisesRegex(RuntimeError, 'CODE_DEPENDENCY_CHANGED'): runner.main()
                key.assert_not_called(); pricing.assert_not_called(); http.assert_not_called()

    def test_runtime_drift_blocks_metadata_and_inference_without_reserving(self):
        h = header()
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory, h)
            verify = MagicMock()
            budget = runner.ExperimentBudget(directory, h, verify=verify)
            budget.case_id = h['case_ids'][0]
            with patch.dict(runner.os.environ, {'OPENROUTER_API_KEY':'gate-a-mock-key'}), \
                patch.object(runner, 'digest', side_effect=self.changed_digest(
                runner.ROOT/'scripts/milestone5c_pilot.py')), patch.object(runner, 'build_opener') as http:
                with self.assertRaises(RuntimeError):
                    runner.ExperimentController(budget, 'unit prompt').decide('unit question', [])
                verify.assert_not_called()
                http.return_value.open.assert_not_called()
                self.assertEqual(budget.calls, 0)


if __name__ == '__main__':
    unittest.main()
