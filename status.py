#!/usr/bin/env python3
"""Check the authenticated bridge endpoint without printing clipboard contents or secrets."""
import argparse
import json
import sys
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('client', 'server'))
    args = parser.parse_args()
    try:
        path = Path.home() / 'Library/Application Support/UUClipboardBridge/config.json'
        config = json.loads(path.read_text())
        endpoint = config['endpoint'] if args.mode == 'client' else 'http://127.0.0.1:' + str(config['port'])
        request = urllib.request.Request(endpoint + '/status', headers={'Authorization': 'Bearer ' + config['token']})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as response:
            value = json.load(response)
        print(json.dumps({k: value[k] for k in ('version', 'applied', 'helperAlive')}, indent=2))
        if not value['helperAlive']:
            return 1
    except Exception as exc:
        print('Status check failed: ' + type(exc).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
