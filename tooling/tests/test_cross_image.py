"""Cross-image lifecycle tests; no Docker daemon or network required."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tooling.common import environment
from tooling.common.process import ToolError


class CrossImageTests(unittest.TestCase):
    def test_unpinned_or_multistage_base_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recipe = root / 'ev3/docker/Dockerfile'
            recipe.parent.mkdir(parents=True)
            for content in ('FROM vendor/image:latest\n',
                            'FROM vendor/image@sha256:' + 'a' * 64 + '\nFROM other/image\n'):
                recipe.write_text(content, encoding='utf-8')
                with patch.object(environment, 'ROOT', root):
                    self.assertRaisesRegex(ToolError, 'digest-pinned FROM', environment.cross_recipe)

    def test_recipe_and_actual_image_both_change_build_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recipe = root / 'ev3/docker/Dockerfile'
            recipe.parent.mkdir(parents=True)
            shutil.copyfile(environment.ROOT / 'ev3/docker/Dockerfile', recipe)
            with patch.object(environment, 'ROOT', root):
                before = environment.toolchain_hash('sha256:' + 'a' * 64)
                self.assertNotEqual(before, environment.toolchain_hash('sha256:' + 'b' * 64))
                recipe.write_bytes(recipe.read_bytes() + b'\n# changed environment recipe\n')
                self.assertNotEqual(before, environment.toolchain_hash('sha256:' + 'a' * 64))

    def test_build_uses_small_context_and_returns_immutable_image_id(self):
        image = 'sha256:' + 'a' * 64
        def docker(arguments, **kwargs):
            if arguments[1] == 'build':
                Path(arguments[arguments.index('--iidfile') + 1]).write_text(image)
            return subprocess.CompletedProcess(arguments, 0, 'linux\n' if arguments[1] == 'info' else '', '')
        with patch.object(environment, 'run', side_effect=docker) as calls:
            selected = environment.cross_image(timeout=42)
        self.assertEqual(selected, image)
        build = next(call.args[0] for call in calls.call_args_list if call.args[0][1] == 'build')
        build_call = next(call for call in calls.call_args_list if call.args[0][1] == 'build')
        self.assertEqual(build_call.kwargs['timeout'], 42)
        self.assertEqual(build[-1], environment.ROOT / 'ev3/docker')
        self.assertEqual(build[build.index('--file') + 1], environment.ROOT / 'ev3/docker/Dockerfile')
        self.assertEqual(calls.call_args_list[-1].args[0], ['docker', 'image', 'inspect', image])

    def test_failed_preparation_does_not_select_an_old_tag(self):
        failure = ToolError('dependency installation failed')
        with patch.object(environment, 'run', side_effect=[subprocess.CompletedProcess([], 0, 'linux', ''), failure]) as calls:
            with self.assertRaises(ToolError) as raised:
                environment.cross_image()
            self.assertIs(raised.exception, failure)
            self.assertEqual(len(calls.call_args_list), 2)

    def test_doctor_inspection_never_builds_an_image(self):
        image = 'sha256:' + 'c' * 64
        with patch.object(environment, 'run', side_effect=[
                subprocess.CompletedProcess([], 0, 'linux', ''),
                subprocess.CompletedProcess([], 0, image, ''),
                subprocess.CompletedProcess([], 0, '', '')]) as calls:
            self.assertEqual(environment.cross_image(prepare=False), image)
        self.assertFalse(any(call.args[0][1] == 'build' for call in calls.call_args_list))
