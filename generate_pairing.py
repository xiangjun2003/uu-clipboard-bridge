#!/usr/bin/env python3
"""Generate a shared secret once; transfer the file privately to the second Mac."""
import argparse
import json
import os
import secrets
from pathlib import Path


def generate(path):
    # Exclusive creation prevents accidentally rotating an existing deployment key.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump({'token': secrets.token_hex(32)}, stream)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'pairing.json')
    args = parser.parse_args()
    try:
        generate(args.output)
    except FileExistsError:
        parser.exit(1, 'File already exists; refusing to replace the pairing key.\n')
    print('Pairing file created. Transfer it privately; never commit or publish it.')


if __name__ == '__main__':
    main()
