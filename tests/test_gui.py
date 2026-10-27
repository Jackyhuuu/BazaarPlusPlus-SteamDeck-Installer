import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox
from deck_installer.gui import Window


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        env = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(root / 'config'), 'XDG_STATE_HOME': str(root / 'state')})
        env.start()
        self.addCleanup(env.stop)
        self.window = Window(startup=False)
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self.window.close)
        self.root = root

    def test_explicit_update_and_current_version_states(self):
        game = self.root / 'game'
        version = game / 'BepInEx/plugins/BazaarPlusPlus.version'
        version.parent.mkdir(parents=True)
        version.write_text('5.6.0.prod')
        self.window.path.setText(str(game))
        self.window.checked('mod', {'version': '5.7.0'})
        self.assertEqual(self.window.current_number.text(), '5.6.0')
        self.assertEqual(self.window.latest_number.text(), '5.7.0')
        self.assertEqual(self.window.install.text(), '更新至 5.7.0')
        version.write_text('5.7.0.prod')
        self.window.show_version()
        self.assertEqual(self.window.version.text(), '已是最新版本')
        self.window.translate(1)
        self.assertEqual(self.window.check.text(), 'Check for updates')
        self.assertEqual(self.window.version.text(), 'You are up to date')

    def test_details_and_advanced_are_collapsed_and_error_is_brief(self):
        self.assertFalse(self.window.logbox.isVisible())
        self.assertFalse(self.window.advanced.isVisible())
        details = 'CERTIFICATE_VERIFY_FAILED\n' + 'technical details ' * 100
        self.window.check_failed('mod', details)
        self.assertLess(len(self.window.status.text()), 100)
        self.assertIn('CERTIFICATE_VERIFY_FAILED', self.window.log.toPlainText())
        self.window.toggle_log()
        self.assertTrue(self.window.logbox.isVisible())
        self.window.toggle_more()
        self.assertTrue(self.window.advanced.isVisible())

    def test_installer_update_uses_verified_project_release_page(self):
        data = {'newer': True, 'tag': 'v0.2.0-preview.9',
                'url': 'https://github.com/Jackyhuuu/BazaarPlusPlus-SteamDeck-Installer/releases/tag/v0.2.0-preview.9'}
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes), \
                patch('deck_installer.gui.QDesktopServices.openUrl') as open_url:
            self.window.checked('installer', data)
        self.assertEqual(open_url.call_args.args[0].toString(), data['url'])

    def test_resolution_entry_copies_full_preset_and_can_return_to_original(self):
        self.window.open_resolution()
        self.app.processEvents()
        self.assertTrue(self.window.advanced.isVisible())
        self.assertTrue(self.window.native_resolution.isChecked())
        self.window.copy_launch_options()
        self.assertIn('-screen-width 1280 -screen-height 800', self.app.clipboard().text())
        self.assertIn('WINEDLLOVERRIDES', self.app.clipboard().text())
        self.window.native_resolution.setChecked(False)
        self.window.copy_launch_options()
        self.assertNotIn('-screen-width', self.app.clipboard().text())
        self.assertIn('1.0.0', self.window.appversion.text())
