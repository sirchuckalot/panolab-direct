#!/usr/bin/env bash
# Build from verified source snapshots; no download, ISE, Docker change or FPGA flash.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
: "${PANOLAB_LAB_MAC:?Set a single-device lab-only MAC, e.g. 02:00:00:00:00:01}"
exec python3 shared/source_registry.py run --project projects/rescue/project.toml -- bash projects/rescue/build_probe.sh
