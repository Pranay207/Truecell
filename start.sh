#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
    exec .venv/bin/python scripts/bootstrap.py "$@"
fi
exec python3 scripts/bootstrap.py "$@"
