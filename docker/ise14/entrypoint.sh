#!/bin/bash
# Preserve the legacy CentOS 6 non-root runuser/UID/license execution model.
set -euo pipefail
uid="${PANO_UID:-1000}"
gid="${PANO_GID:-1000}"
[[ "$uid" =~ ^[0-9]+$ && "$gid" =~ ^[0-9]+$ ]] || { echo "invalid UID/GID" >&2; exit 2; }
if ! getent group "$gid" >/dev/null 2>&1; then groupadd -g "$gid" pano; fi
if ! getent passwd "$uid" >/dev/null 2>&1; then useradd -u "$uid" -g "$gid" -d /home/ise -s /bin/bash ise; fi
mkdir -p /results/jobs
chown "$uid:$gid" /home/ise /results /results/jobs
chmod 0700 /results/jobs
export HOME=/home/ise
export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-/licenses/Xilinx.lic}"
printf -v token_quoted '%q' "${PANOLAB_MCP_TOKEN:-}"
# The official Docker MCP Gateway communicates over stdio and does not set
# an HTTP bearer token; preserve the selected transport across runuser.
transport="${PANOLAB_MCP_TRANSPORT:-http}"
case "$transport" in stdio|http) ;; *) echo "Invalid MCP transport" >&2; exit 2;; esac
printf -v transport_quoted '%q' "$transport"
printf -v license_quoted '%q' "$XILINXD_LICENSE_FILE"
mode="${1:-mcp}"
case "$mode" in
  mcp)
    exec runuser -s /bin/bash -c "
      export HOME=/home/ise
      export XILINXD_LICENSE_FILE=$license_quoted
      export PANOLAB_MCP_TOKEN=$token_quoted
      export PANOLAB_MCP_TRANSPORT=$transport_quoted
      exec /usr/local/bin/panolab-ise-mcp
    " ise
    ;;
  shell)
    # Local container maintenance, never an MCP-exposed remote shell.
    exec runuser -s /bin/bash -c "
      export HOME=/home/ise
      export XILINXD_LICENSE_FILE=$license_quoted
      if [ -r /opt/Xilinx/14.7/ISE_DS/settings64.sh ]; then . /opt/Xilinx/14.7/ISE_DS/settings64.sh; fi
      exec /bin/bash -i
    " ise
    ;;
  *)
    echo "Supported modes: mcp (default), shell (local maintenance only)" >&2
    exit 2
    ;;
esac
