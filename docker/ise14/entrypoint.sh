#!/bin/bash
# ISE 14.7 rootless vendor worker. Container UID 0 maps to the ordinary
# laptop owner, not host root. Docker must drop capabilities, isolate the
# license-bound virtual Ethernet identity on an INTERNAL network, disable
# new privileges, and use a read-only root filesystem.
#
# Do not create Linux users, modify /etc, run setuid, or chown bind mounts:
# these operations are incompatible with the restricted rootless runtime.
set -euo pipefail
umask 077

[[ "$(id -u)" == 0 ]] || { echo "ISE worker requires rootless container UID 0" >&2; exit 2; }
mapped_uid="$(awk '$1 == 0 {print $2; exit}' /proc/self/uid_map)"
[[ "$mapped_uid" =~ ^[0-9]+$ && "$mapped_uid" != 0 ]] || {
  echo "Refusing ISE worker without a non-root host UID mapping" >&2
  exit 2
}
export HOME=/home/ise
export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-/licenses/Xilinx.lic}"
[[ -d "$HOME" && -d /results && -d /projects ]] || {
  echo "ISE worker required isolated mounts are missing" >&2
  exit 2
}
mkdir -p /results/jobs
chmod 0700 /results/jobs

transport="${PANOLAB_MCP_TRANSPORT:-http}"
case "$transport" in stdio|http) ;; *) echo "Invalid MCP transport" >&2; exit 2;; esac

case "${1:-mcp}" in
  mcp)
    export PANOLAB_MCP_TRANSPORT="$transport"
    exec /usr/local/bin/panolab-ise-mcp
    ;;
  shell)
    # Local-only maintenance, not exposed as an MCP action.
    if [[ -r /opt/Xilinx/14.7/ISE_DS/settings64.sh ]]; then
      . /opt/Xilinx/14.7/ISE_DS/settings64.sh
    fi
    exec /bin/bash -i
    ;;
  *)
    echo "Supported modes: mcp (default), shell (local maintenance only)" >&2
    exit 2
    ;;
esac
