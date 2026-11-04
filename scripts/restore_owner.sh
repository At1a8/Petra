#!/bin/sh
# Give what root wrote back to the owner of the checkout it lives in.
#
# Petra runs as root inside the container; the checkouts it mounts belong to a host user, whose git
# fails on root-owned files in .git (knowledge/env_hygiene.md). Run it after every git write and before
# handing over a push command:
#
#   scripts/restore_owner.sh <framework_dir>/.git <worktree> <run_dir>
#
# Each path goes to the owner of its closest ancestor that is not root's. Not root: nothing to do.
[ "$(id -u)" = 0 ] || exit 0
status=0
for p in "$@"; do
  [ -e "$p" ] || continue
  d=$(cd "$(dirname "$p")" && pwd -P) || { status=1; continue; }
  while [ "$d" != / ] && [ "$(stat -c %u "$d")" = 0 ]; do
    d=$(dirname "$d")
  done
  owner=$(stat -c %u:%g "$d")
  case "$owner" in 0:*) continue ;; esac
  chown -R "$owner" "$p" || status=1
done
exit "$status"
