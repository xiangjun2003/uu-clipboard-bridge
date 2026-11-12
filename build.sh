#!/bin/sh
set -eu
cd "$(dirname "$0")"
# Compile natively on each Mac; no prebuilt executable is distributed.
xcrun swiftc -O pasteboard.swift -o pasteboard
printf '%s\n' 'Built pasteboard for this Mac.'
