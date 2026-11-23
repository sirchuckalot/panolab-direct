#!/usr/bin/env bash
# One-command laptop rootless deployment. The audited implementation lives in host/.
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd -P)"
exec bash "$root/host/rootless-install.sh" "$@"
