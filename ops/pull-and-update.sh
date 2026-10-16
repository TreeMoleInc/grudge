#!/usr/bin/env bash
#
# The everyday update command: downloads the latest code from GitHub, then
# deploys it (ops/update.sh - migrations, website rebuild, service restart).
#
# HOW TO RUN, on the server:
#   sudo /opt/grudge/ops/pull-and-update.sh
#
# Run it as root (via sudo) by whoever cloned the repo - that's the account
# with GitHub access. The code is owned by the `grudge` service user, so this
# pulls as root and hands ownership back afterward.
#
# The whole script is wrapped in main() and ends with `exit`: bash reads a
# script as it runs, so without that, the `git pull` below replacing this very
# file mid-run could make bash continue from the wrong place.
#
main() {
  set -euo pipefail

  local code_dir=/opt/grudge

  [ "$(id -u)" -eq 0 ] || { echo "STOP: Run this with sudo." >&2; exit 1; }
  [ -d "$code_dir/.git" ] || { echo "STOP: No git repo at $code_dir - run ops/install.sh first." >&2; exit 1; }

  printf '\n\033[1;34m=== Pulling the latest code from GitHub ===\033[0m\n'
  # safe.directory: git refuses to touch a repo owned by a different user
  # ("dubious ownership"), and the repo is owned by `grudge`, not root.
  local git_root=(git -c "safe.directory=$code_dir" -C "$code_dir")
  local before after
  before="$("${git_root[@]}" rev-parse HEAD)"
  "${git_root[@]}" pull --ff-only
  after="$("${git_root[@]}" rev-parse HEAD)"
  if [ "$before" = "$after" ]; then
    echo "  Already up to date - nothing new to pull. Redeploying anyway, in case an earlier update stopped partway."
  else
    echo "  Updated ${before:0:8} -> ${after:0:8}"
  fi

  # Files pulled as root are root-owned; the services and the website build
  # run as `grudge` and need to own them.
  chown -R grudge:grudge "$code_dir"

  # exec, not a plain call: this script is done after handing over to the
  # (possibly just-updated) update.sh.
  exec "$code_dir/ops/update.sh"
}

main "$@"
exit
