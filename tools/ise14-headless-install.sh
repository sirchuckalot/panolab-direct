#!/usr/bin/env bash
# One-time trusted bootstrap: install native ISE 14.7 from the owner's private
# pre-extracted Linux installer INSIDE the established CentOS 6 Docker image.
# Not an MCP tool and not a license/flash/programming operation.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image="${PANOLAB_ISE_IMAGE:-panolab-direct-ise14-mcp:local}"
installer="${ISE_INSTALLER_DIR:?Set private ISE_INSTALLER_DIR to extracted native Linux installer root}"
target="${ISE_INSTALL_PATH:?Set private ISE_INSTALL_PATH to new empty host Xilinx installation root}"
batch="$root/docker/ise14/ise-system-edition.batch"

[[ -f "$batch" ]] || { echo "Missing tested System Edition batch selection" >&2; exit 2; }
[[ -x "$installer/bin/lin64/batchxsetup" && -x "$installer/xsetup" ]] || {
  echo "Expected native 14.7 Linux installer with bin/lin64/batchxsetup and xsetup" >&2; exit 2; }
[[ -d "$target" ]] || { echo "Create an EMPTY, private install directory before starting: $target" >&2; exit 2; }
if find "$target" -mindepth 1 -print -quit | grep -q .; then
  echo "Refusing to overwrite existing ISE installation: $target" >&2
  exit 3
fi
if [[ ! -w "$target" ]]; then
  echo "Target is not writable by this user: $target" >&2
  exit 3
fi
command -v docker >/dev/null || { echo "Docker CLI is required for initial bootstrap" >&2; exit 127; }

echo "Headless ISE 14.7 System Edition install from private native media"
echo "This preserves the prior USB3300 batchxsetup approach and does not run VNC."
echo "Installer archive and license are not copied to a Docker image or repository."
echo "User must review Xilinx license terms and approve this installation separately."
[[ "${PANOLAB_APPROVE_ISE_INSTALL:-}" == "YES" ]] || {
  echo "Set PANOLAB_APPROVE_ISE_INSTALL=YES after reviewing license and destination." >&2
  exit 4
}
docker image inspect "$image" >/dev/null || {
  echo "Build the ISE runtime image first (trusted bootstrap): $image" >&2; exit 4; }

# Run installation solely inside the legacy runtime with a private writable
# install location; no Docker socket or agent-controlled command runner exposed.
docker run --rm --platform linux/amd64 \
  --user "$(id -u):$(id -g)" \
  --entrypoint /bin/bash \
  -e HOME=/tmp -e TERM=xterm \
  -v "$installer:/installer:ro" \
  -v "$target:/opt/Xilinx" \
  -v "$batch:/config/ise-system-edition.batch:ro" \
  "$image" -c 'set -e; cd /installer; yes | ./bin/lin64/batchxsetup --batch /config/ise-system-edition.batch'

test -f "$target/14.7/ISE_DS/settings64.sh" || {
  echo "Installer exited without required 14.7/ISE_DS/settings64.sh" >&2; exit 5; }
echo "Headless ISE install completed. Next verify toolchain through the embedded MCP server."
