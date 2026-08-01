#!/usr/bin/env bash
set -Eeuo pipefail

REPO="${LIFEOS_REPO:-${HOME}/truthlayer-ai}"
EXPECTED_ORIGIN="tecinocryptlifeos/lifeosai"
TARGET_BRANCH="architecture/split-platform"

[ -d "$REPO/.git" ] || { printf 'ABORT: repository not found at %s\n' "$REPO"; exit 1; }
cd "$REPO"

REMOTE="$(git remote get-url origin)"
case "$REMOTE" in
  *github.com/tecinocryptlifeos/lifeosai|*github.com/tecinocryptlifeos/lifeosai.git) ;;
  *) printf 'ABORT: unexpected origin: %s\n' "$REMOTE"; exit 1 ;;
esac

CURRENT="$(git branch --show-current)"
[ "$CURRENT" = "$TARGET_BRANCH" ] || {
  printf 'ABORT: current branch is %s; expected %s\n' "$CURRENT" "$TARGET_BRANCH"
  exit 1
}

printf 'REPOSITORY=%s\n' "$EXPECTED_ORIGIN"
printf 'BRANCH=%s\n' "$CURRENT"
printf 'MAIN_REFERENCE=%s\n' "$(git rev-parse refs/heads/main)"
printf 'HEAD=%s\n' "$(git rev-parse HEAD)"
printf 'STATUS_START\n'
git status -sb
printf 'STATUS_END\nTERMUX_PREFLIGHT=PASS\n'
