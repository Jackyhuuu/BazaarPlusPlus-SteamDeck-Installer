import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from deck_installer import core


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root / 'game'
        self.game.mkdir()
        (self.game / 'TheBazaar.exe').write_bytes(b'MZ game')
        (self.game / 'TheBazaar_Data').mkdir()
        self.stage = self.root / 'stage'
        self.stage.mkdir()

    def file(self, root, name, data):
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def test_manifest_requires_hash_size_https_and_windows(self):
        manifest = {'version': '5.7.0', 'downloads': {'windows-x86_64': {
            'url': 'https://bppinstaller.bazaarplusplus.com/5.7.0/app.exe',
            'size': 12, 'sha256': 'a' * 64}}}
        self.assertEqual(core.parse_manifest(manifest)['version'], '5.7.0')
        for key, bad in [('sha256', ''), ('size', -1), ('url', 'http://bppinstaller.bazaarplusplus.com/app.exe'),
                         ('url', 'https://evil.example/app.exe')]:
            copy = json.loads(json.dumps(manifest))
            copy['downloads']['windows-x86_64'][key] = bad
            with self.assertRaises(core.InstallError):
                core.parse_manifest(copy)

    def test_wrong_hash_rejected(self):
        p = self.file(self.root, 'app.exe', b'test')
        with self.assertRaises(core.InstallError):
            core.verify(p, {'size': 4, 'sha256': '0' * 64})

    def test_redirect_cannot_leave_official_hosts(self):
        with self.assertRaises(core.InstallError):
            core.ReleaseRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example/payload.exe')

    def test_zip_traversal_symlink_unknown_and_duplicate_rejected(self):
        for name in ['../escape', '/tmp/escape', 'BepInEx/../escape', 'TheBazaar.exe', 'BepInEx\\plugins\\evil.dll']:
            archive = self.root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr(name, b'bad')
            with self.assertRaises(ValueError):
                core.stage_payload(archive, self.stage)
        archive = self.root / 'link.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            info = zipfile.ZipInfo('winhttp.dll')
            info.external_attr = 0o120777 << 16
            z.writestr(info, '/etc/passwd')
        with self.assertRaises(ValueError):
            core.stage_payload(archive, self.stage)

    def test_install_restore_preserves_game_settings_and_other_mods(self):
        name = 'BepInEx/plugins/BazaarPlusPlus.dll'
        self.file(self.game, name, b'old mod')
        settings = self.file(self.game, 'TheBazaar_Data/settings.json', b'1280x800')
        config = self.file(self.game, 'BepInEx/config/BazaarPlusPlus.cfg', b'user preferences')
        other = self.file(self.game, 'BepInEx/plugins/OtherMod.dll', b'other')
        self.file(self.stage, name, b'new mod')
        self.file(self.stage, 'winhttp.dll', b'bootstrap')
        backup = core.install_payload(self.game, self.stage, [name, 'winhttp.dll'], 'test', 'a' * 64)
        self.assertEqual((self.game / name).read_bytes(), b'new mod')
        self.assertTrue(backup.is_dir())
        core.restore_latest(self.game)
        self.assertEqual((self.game / name).read_bytes(), b'old mod')
        self.assertFalse((self.game / 'winhttp.dll').exists())
        self.assertFalse((self.game / core.RECEIPT).exists())
        self.assertEqual(settings.read_bytes(), b'1280x800')
        self.assertEqual(config.read_bytes(), b'user preferences')
        self.assertEqual(other.read_bytes(), b'other')

    def test_mid_install_failure_rolls_back(self):
        names = ['winhttp.dll', 'doorstop_config.ini']
        for n in names:
            self.file(self.game, n, b'old')
            self.file(self.stage, n, b'new')
        real_copy = core.atomic_copy
        failed = False
        def fail_once(src, dest):
            nonlocal failed
            if Path(src) == self.stage / names[1] and not failed:
                failed = True
                raise OSError('injected disk failure')
            return real_copy(src, dest)
        with patch.object(core, 'atomic_copy', side_effect=fail_once):
            with self.assertRaises(OSError):
                core.install_payload(self.game, self.stage, names, 'test', 'a' * 64)
        self.assertTrue(failed)
        for n in names:
            self.assertEqual((self.game / n).read_bytes(), b'old')

    def test_update_removes_only_receipted_stale_files(self):
        a, b = 'BepInEx/plugins/BazaarPlusPlus.dll', 'BepInEx/plugins/BazaarPlusPlus.Localization.dll'
        for n in [a, b]:
            self.file(self.stage, n, b'v1')
        other = self.file(self.game, 'BepInEx/plugins/OtherMod.dll', b'other')
        core.install_payload(self.game, self.stage, [a, b], 'v1', 'a' * 64)
        self.file(self.stage, a, b'v2')
        core.install_payload(self.game, self.stage, [a], 'v2', 'b' * 64)
        self.assertFalse((self.game / b).exists())
        self.assertEqual(other.read_bytes(), b'other')
        core.restore_latest(self.game)
        self.assertEqual((self.game / b).read_bytes(), b'v1')

    def test_pending_transaction_recovers_after_interruption(self):
        name = 'winhttp.dll'
        self.file(self.game, name, b'partial')
        backup = self.game / core.STATE / 'backups/interrupted'
        self.file(backup / 'files', name, b'old')
        core.write_json(backup / 'transaction.json', {'files': [name], 'absent': [], 'status': 'pending'})
        core.recover_pending(self.game)
        self.assertEqual((self.game / name).read_bytes(), b'old')

    def test_destination_symlink_rejected_before_writing(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.game / 'BepInEx').symlink_to(outside, target_is_directory=True)
        name = 'BepInEx/plugins/BazaarPlusPlus.dll'
        self.file(self.stage, name, b'mod')
        with self.assertRaises(ValueError):
            core.install_payload(self.game, self.stage, [name], 'test', 'a' * 64)
        self.assertEqual(list(outside.iterdir()), [])

    def test_detection_external_steam_library(self):
        home = self.root / 'home'
        library = self.root / 'SD card'
        game = library / 'steamapps/common/The Bazaar'
        game.mkdir(parents=True)
        (game / 'TheBazaar.exe').write_bytes(b'game')
        (game / 'TheBazaar_Data').mkdir()
        self.file(home, '.local/share/Steam/steamapps/libraryfolders.vdf',
                  ('"libraryfolders" { "1" { "path" "' + str(library) + '" } }').encode())
        self.assertIn(game.resolve(), core.discover(home, self.root / 'media'))

    def test_detection_config_vdf_and_nested_manifest_game(self):
        home = self.root / 'home'
        library = self.root / 'custom-library'
        game = library / 'steamapps/common/custom-name/Windows/Release'
        game.mkdir(parents=True)
        (game / 'TheBazaar.exe').write_bytes(b'game')
        (game / 'TheBazaar_Data').mkdir()
        self.file(home, '.steam/root/config/libraryfolders.vdf',
                  ('"libraryfolders" { "1" "' + str(library) + '" }').encode())
        self.file(library, 'steamapps/appmanifest_123.acf',
                  b'"AppState" { "name" "The Bazaar" "installdir" "custom-name" }')
        messages = []
        games = core.discover(home, self.root / 'media', lambda zh, en: messages.append(en))
        self.assertIn(game.resolve(), games)
        self.assertTrue(any('Steam manifest location:' in m for m in messages))

    def test_detection_sd_card_nested_steamlibrary_without_vdf(self):
        media = self.root / 'media'
        game = media / 'deck/card/SteamLibrary/steamapps/common/The Bazaar/Windows'
        game.mkdir(parents=True)
        (game / 'TheBazaar.exe').write_bytes(b'game')
        (game / 'TheBazaar_Data').mkdir()
        self.assertIn(game.resolve(), core.discover(self.root / 'home', media))

    def test_detection_unreadable_library_does_not_abort_other_libraries(self):
        home = self.root / 'home'
        game = home / '.local/share/Steam/steamapps/common/The Bazaar'
        game.mkdir(parents=True)
        (game / 'TheBazaar.exe').write_bytes(b'game')
        (game / 'TheBazaar_Data').mkdir()
        broken = home / '.steam/root/steamapps/common'
        broken.mkdir(parents=True)
        original = Path.iterdir
        def denied(path):
            if path == broken.resolve():
                raise PermissionError('simulated permission failure')
            return original(path)
        messages = []
        with patch.object(Path, 'iterdir', denied):
            games = core.discover(home, self.root / 'media', lambda zh, en: messages.append(en))
        self.assertIn(game.resolve(), games)
        self.assertTrue(any('Cannot read:' in m for m in messages))

    @unittest.skipUnless(os.environ.get('BPP_TEST_EXE'), 'Set BPP_TEST_EXE to test a real official installer')
    def test_real_exe_install_update_restore(self):
        exe = os.environ['BPP_TEST_EXE']
        digest = os.environ['BPP_TEST_SHA256']
        version = core.run_install(self.game, exe, digest)
        self.assertTrue((self.game / 'BepInEx/plugins/BazaarPlusPlus.dll').is_file())
        self.assertTrue((self.game / 'winhttp.dll').is_file())
        core.run_install(self.game, exe, digest)
        core.restore_latest(self.game)
        core.restore_latest(self.game)
        self.assertFalse((self.game / 'winhttp.dll').exists())
        self.assertTrue(version.startswith('5.7.0'))


if __name__ == '__main__':
    unittest.main()
