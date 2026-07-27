#!/usr/bin/env bash
# Credential loader. Copy to ops/.env (gitignored) and fill in, then:
#   ./ops/env.sh python3 ops/run_cycle.py replies
set -a
[ -f "$(dirname "$0")/.env" ] && . "$(dirname "$0")/.env"
set +a
exec "$@"
