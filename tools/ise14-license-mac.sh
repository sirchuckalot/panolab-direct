#!/usr/bin/env bash
# Local bootstrap helper only (NOT an agent-facing build interface).
# Extracts Xilinx node-locked Ethernet HOSTID from private license file
# and exports ISE_MAC for the original legacy Docker networking behavior.
# Usage: source tools/ise14-license-mac.sh /private/path/Xilinx.lic
[[ "${BASH_SOURCE[0]}" != "$0" ]] || { echo "Source this script: source tools/ise14-license-mac.sh LICENSE" >&2; exit 2; }
file="${1:?license file required}"
[[ -r "$file" && -s "$file" ]] || { echo "license missing/unreadable" >&2; return 1; }
mapfile -t ids < <(grep -v '^[[:space:]]*#' "$file" | grep -Eo 'HOSTID=[^[:space:];]+' | cut -d= -f2 | tr 'A-F' 'a-f' | sort -u)
if [[ "${#ids[@]}" -ne 1 || ! "${ids[0]}" =~ ^[0-9a-f]{12}$ ]]; then
  echo "Expected exactly one 12-hex Ethernet HOSTID; no MAC exported" >&2
  return 1
fi
id="${ids[0]}"
export ISE_MAC="${id:0:2}:${id:2:2}:${id:4:2}:${id:6:2}:${id:8:2}:${id:10:2}"
echo "ISE_MAC exported from local license; do not publish the value."
