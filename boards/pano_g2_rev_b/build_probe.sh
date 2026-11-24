#!/usr/bin/env bash
# Reuse pinned upstream sources inside a rootless developer container.
# This script does not fetch, install, flash, use sudo, or alter the host.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
upstream="${PANOLAB_RESCUE_UPSTREAM:?set PANOLAB_RESCUE_UPSTREAM to a directory containing pinned litex/liteeth/litespi/migen/litex-boards source checkouts}"
pydeps="${PANOLAB_RESCUE_PYDEPS:?set PANOLAB_RESCUE_PYDEPS to isolated Python dependencies}"
bin_dir="${PANOLAB_RESCUE_BIN:-}"
lab_mac="${PANOLAB_LAB_MAC:?set PANOLAB_LAB_MAC to an explicit per-board locally administered unicast MAC, e.g. 02:00:00:00:00:01; NOT a production identity implementation}"
out="${PANOLAB_RESCUE_OUT:-$here/build/probe}"
python="${PYTHON:-python3}"
expected=(
  "litex:afed66238638fac1d1e13c3edd6568cdccea5356"
  "litex-boards:2ccda1274d9a00088af3407bc93f0c7dd4892981"
  "liteeth:a54c730c323f271e5b5a33d48df54f6ce2d58c0a"
  "litespi:a5a0090ad16c2bebe0cb01dcc07e843b558ca4f6"
  "migen:e19524c963a8342952840983047557707fbe0b6a"
  "picolibc:16ff442da4b92e28d0753fabed18ad4a15254498"
  "pythondata-software-picolibc:6a13ccce7c575b32c102dd9dc52178505b81fe39"
)
for pair in "${expected[@]}"; do
  name="${pair%%:*}"
  wanted="${pair#*:}"
  observed="$(git -C "$upstream/$name" rev-parse HEAD 2>/dev/null || true)"
  if [[ "$observed" != "$wanted" ]]; then
    echo "Pin mismatch: $name expected=$wanted observed=${observed:-missing}" >&2
    exit 2
  fi
done
export PYTHONPATH="$here:$pydeps:$upstream/pythondata-software-picolibc:$upstream/migen:$upstream/litex:$upstream/litex-boards:$upstream/liteeth:$upstream/litespi${PYTHONPATH:+:$PYTHONPATH}"
if [[ -n "$bin_dir" ]]; then export PATH="$bin_dir:$PATH"; fi
command -v riscv64-unknown-elf-gcc >/dev/null || {
  echo "RISC-V cross-compiler not available; supply a workspace-local toolchain in PANOLAB_RESCUE_BIN" >&2
  exit 3
}
command -v meson >/dev/null || {
  echo "Meson missing; supply isolated tools in PANOLAB_RESCUE_BIN" >&2
  exit 3
}
[[ -f "$upstream/pythondata-software-picolibc/pythondata_software_picolibc/data/libc/stdio/printf.c" ]] || { echo "Missing pinned Picolibc layout; rebuild image recipe" >&2; exit 3; }
mkdir -p "$out"
"$python" "$here/rescue_soc.py" --lab-mac "$lab_mac" --generate --out "$out"
echo "LiteX BIOS + Verilog/UCF generated at $out"
echo "NOTE: --generate does not run ISE, create a .bit file, or program an FPGA."
