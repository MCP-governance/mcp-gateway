#!/bin/bash
# Driver for the isolated termination/dispatch lab, run from WSL (key-based ssh to the solution appliance).
# Copies this tree to /tmp/wbs-c-src there and runs termination_dispatch_remote.sh. Touches only wbs-c-*
# containers/network and /tmp/wbs-c-*; the product stack is never started, stopped or entered.
#
#   tests/termination_dispatch_lab.sh up
#   tests/termination_dispatch_lab.sh run dispatch_intent_pg_check.py
#   tests/termination_dispatch_lab.sh down
set -uo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
HOST=${LAB_APPLIANCE:-user@100.83.175.111}
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=15 "$HOST")
tar czf - --exclude=__pycache__ -C "$HERE" gateway/app tests registry opa db \
  | "${SSH[@]}" 'mkdir -p /tmp/wbs-c-src && tar xzf - -C /tmp/wbs-c-src' || exit 1
"${SSH[@]}" bash /tmp/wbs-c-src/tests/termination_dispatch_remote.sh "$@" </dev/null
