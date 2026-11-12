import json
import os
import stat
import tempfile
import plistlib
from unittest.mock import patch

import install
import uninstall
import unittest
from pathlib import Path

from generate_pairing import generate


class PairingTests(unittest.TestCase):
    def test_secret_permissions_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'pairing.json'
            previous = os.umask(0)
            try:
                generate(path)
            finally:
                os.umask(previous)
            original = path.read_bytes()
            self.assertEqual(len(bytes.fromhex(json.loads(original)['token'])), 32)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                generate(path)
            self.assertEqual(path.read_bytes(), original)

    def test_distinct_pairings(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / 'a.json', Path(directory) / 'b.json'
            generate(a)
            generate(b)
            self.assertNotEqual(a.read_bytes(), b.read_bytes())


class InstallationTests(unittest.TestCase):
    def test_install_switch_role_and_uninstall_preserves_config(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            pairing = home / 'pairing.json'
            generate(pairing)
            config = home / 'Library/Application Support/UUClipboardBridge/config.json'
            agents = home / 'Library/LaunchAgents'
            previous = os.umask(0o077)
            try:
                with patch('pathlib.Path.home', return_value=home), \
                     patch('sys.platform', 'darwin'), patch('os.getuid', return_value=501), \
                     patch('subprocess.run') as run:
                    with patch('sys.argv', ['install.py', 'server', '--pairing', str(pairing)]):
                        install.main()
                    original = config.read_bytes()
                    self.assertEqual(json.loads(original)['token'], json.loads(pairing.read_text())['token'])
                    self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)
                    server_plist = agents / 'local.uuclipboardbridge.server.plist'
                    spec = plistlib.loads(server_plist.read_bytes())
                    self.assertTrue(spec['RunAtLoad'])
                    self.assertTrue(spec['KeepAlive'])
                    self.assertIn('server', spec['ProgramArguments'])
                    self.assertEqual(run.call_args.args[0][1], 'bootstrap')
                    # Reinstallation can reuse the installed config before it is overwritten.
                    with patch('sys.argv', ['install.py', 'client', '--pairing', str(config)]):
                        install.main()
                    self.assertFalse(server_plist.exists())
                    self.assertEqual(config.read_bytes(), original)
                    uninstall.main()
                    self.assertFalse((agents / 'local.uuclipboardbridge.client.plist').exists())
                    self.assertEqual(config.read_bytes(), original)
            finally:
                os.umask(previous)

if __name__ == '__main__':
    unittest.main()
