"""Release plumbing: one version source, pinned CI dependencies."""
import re
import unittest
from pathlib import Path

import akis
from akis import update_service

ROOT = Path(__file__).resolve().parent.parent


class ReleaseConfigTests(unittest.TestCase):
    def test_single_version_source(self):
        self.assertRegex(akis.__version__, r'^\d+\.\d+\.\d+$')
        self.assertEqual(update_service.VERSION, akis.__version__)
        installer = (ROOT / 'installer.iss').read_text(encoding='utf-8')
        workflow = (ROOT / '.github/workflows/windows-build.yml').read_text(encoding='utf-8')
        # The only literal version allowed in the installer is the dev fallback.
        self.assertEqual(re.findall(r'#define AppVersion "([^"]+)"', installer), ['0.0.0-dev'])
        release_lines = [line for line in workflow.splitlines() if 'gh release' in line]
        self.assertTrue(release_lines)
        for line in release_lines:
            self.assertNotRegex(line, r'\d+\.\d+\.\d+')
        self.assertIn('/DAppVersion=$env:APP_VERSION', workflow)

    def test_workflow_actions_are_pinned_to_commits(self):
        workflow = (ROOT / '.github/workflows/windows-build.yml').read_text(encoding='utf-8')
        uses = re.findall(r'uses:\s*([^\s#]+)', workflow)
        self.assertTrue(uses)
        for action in uses:
            with self.subTest(action=action):
                self.assertRegex(action, r'@[0-9a-f]{40}$')
        self.assertRegex(workflow, r"choco install ffmpeg --version=\$env:FFMPEG_CHOCO_VERSION")


if __name__ == '__main__':
    unittest.main()
