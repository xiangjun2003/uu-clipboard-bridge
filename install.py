#!/usr/bin/env python3
"""Install one role as a per-user macOS LaunchAgent (run without sudo)."""
import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('client', 'server'))
    parser.add_argument('--pairing', type=Path, default=Path(__file__).resolve().parent / 'pairing.json')
    args = parser.parse_args()
    if sys.platform != 'darwin' or os.getuid() == 0:
        parser.error('Run as the logged-in macOS user, without sudo.')
    source = Path(__file__).resolve().parent
    if not os.access(source / 'pasteboard', os.X_OK):
        parser.error('Build the helper first: sh build.sh')
    try:
        token = json.loads(args.pairing.read_text())['token']
        if not isinstance(token, str) or len(token) != 64:
            raise ValueError('expected a 64-character hexadecimal token')
        bytes.fromhex(token)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error('Invalid pairing file: ' + str(exc))
    os.umask(0o077)
    dest = Path.home() / 'Library/Application Support/UUClipboardBridge'
    dest.mkdir(parents=True, exist_ok=True)
    os.chmod(dest, 0o700)
    agents = Path.home() / 'Library/LaunchAgents'
    agents.mkdir(parents=True, exist_ok=True)
    domain = 'gui/' + str(os.getuid())
    # Only one role per user; stop an earlier installation before replacing files.
    for role in ('client', 'server'):
        label = 'local.uuclipboardbridge.' + role
        subprocess.run(['launchctl', 'bootout', domain + '/' + label],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        previous = agents / (label + '.plist')
        if previous.exists():
            previous.unlink()
    for name in ('bridge.py', 'pasteboard', 'pasteboard.swift', 'install.py'):
        if (source / name).resolve() != (dest / name).resolve():
            shutil.copy2(source / name, dest / name)
    os.chmod(dest / 'pasteboard', 0o700)
    target = dest / 'config.json'
    target.write_text(json.dumps({'token': token, 'port': 24130,
                                  'endpoint': 'http://127.0.0.1:24131'}))
    os.chmod(target, 0o600)
    label = 'local.uuclipboardbridge.' + args.mode
    plist = agents / (label + '.plist')
    for suffix in ('.log', '.error.log'):
        log = dest / (args.mode + suffix)
        log.touch(exist_ok=True)
        log.chmod(0o600)
    spec = {'Label': label, 'ProgramArguments': [sys.executable, str(dest / 'bridge.py'),
            args.mode, '--config', str(target)], 'RunAtLoad': True, 'KeepAlive': True,
            'ThrottleInterval': 10, 'ProcessType': 'Background', 'Umask': 0o077,
            'StandardOutPath': str(dest / (args.mode + '.log')),
            'StandardErrorPath': str(dest / (args.mode + '.error.log'))}
    plist.write_bytes(plistlib.dumps(spec))
    plist.chmod(0o600)
    subprocess.run(['launchctl', 'bootstrap', domain, str(plist)], check=True)
    print('Installed ' + args.mode + '; starts after this user logs in.')
    print('Check service state and test clipboard transfer as described in README.md.')


if __name__ == '__main__':
    main()
