#!/usr/bin/env bash
# macOS: double-click in Finder. Linux: run from a terminal.
cd "$(dirname "$0")"
exec bash scripts/native/bootstrap.sh install "$@"
