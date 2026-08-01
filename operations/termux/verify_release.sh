#!/usr/bin/env bash
set -Eeuo pipefail

REPO="${LIFEOS_REPO:-${HOME}/truthlayer-ai}"
cd "$REPO"
[ "$(git branch --show-current)" = "architecture/split-platform" ] || {
  printf 'ABORT: split-platform branch is not active\n'
  exit 1
}

python -m unittest discover -s tests -v
npm --prefix services/edge-gateway test
npm --prefix services/edge-gateway run check
python apps/web/build.py
python -m compileall -q app services/failover-python apps/web infrastructure/cloudflare operations
printf 'TERMUX_RELEASE_VERIFICATION=PASS\n'
