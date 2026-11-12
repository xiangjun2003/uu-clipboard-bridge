#!/usr/bin/env python3
"""Stop both bridge roles and remove their login entries, preserving configuration/logs."""
import os
import subprocess
import sys
from pathlib import Path


def main():
    if sys.platform != 'darwin' or os.getuid() == 0:
        raise SystemExit('Run as the logged-in macOS user, without sudo.')
    for role in ('client', 'server'):
        label = 'local.uuclipboardbridge.' + role
        subprocess.run(['launchctl', 'bootout', 'gui/' + str(os.getuid()) + '/' + label],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        plist = Path.home() / 'Library/LaunchAgents' / (label + '.plist')
        if plist.exists():
            plist.unlink()
    print('Removed login entries and requested service stop. Verify with launchctl print.')
    print('Configuration/logs preserved in ~/Library/Application Support/UUClipboardBridge.')


if __name__ == '__main__':
    main()
