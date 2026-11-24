#!/usr/bin/env bash
# Reuse pinned upstream sources inside a rootless developer container.
# This script does not fetch, install, flash, use sudo, or alter the host.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Invoked by the source-registry runner only; it verifies all imported source bytes.
[[ "${PANOLAB_SOURCE_VERIFIED:-}" == 1 ]] || {
  echo "Use bash projects/rescue/build.sh to verify PanoLab source snapshots" >&2; exit 3;
}
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
lab_mac="${PANOLAB_LAB_MAC:?Set a single-device lab-only MAC, not a production identity}"
out="${PANOLAB_RESCUE_OUT:?Run through the source registry for isolated output}"
python="${PYTHON:-python3}"
command -v riscv64-unknown-elf-gcc >/dev/null || {
  echo "RISC-V cross-compiler not available; supply a workspace-local toolchain in PANOLAB_RESCUE_BIN" >&2
  exit 3
}
command -v meson >/dev/null || {
  echo "Meson missing; supply isolated tools in PANOLAB_RESCUE_BIN" >&2
  exit 3
}
"$python" -c 'import pythondata_software_picolibc as p; from pathlib import Path; assert (Path(p.data_location)/"libc/stdio/printf.c").is_file()' ||
  { echo "Missing Picolibc source imported into PanoLab" >&2; exit 3; }
mkdir -p "$out"
# Keep the complete build log with the artifacts, and fail on real compiler/linker diagnostics.
"$python" "$here/soc/rescue_soc.py" --lab-mac "$lab_mac" --generate --out "$out" 2>&1 | tee "$out/build.log"
if grep -Ei "warning:|error:" "$out/build.log"; then
  echo "Unexpected LiteX BIOS compile/link diagnostics; review upstream compatibility patches" >&2
  exit 5
fi
echo "BIOS_BUILD_DIAGNOSTICS=ZERO"
# Prove warning-free BIOS linking rather than masking linker diagnostics.
elf="$out/software/bios/bios.elf"
[[ -s "$elf" ]] || { echo "Compiled BIOS ELF missing" >&2; exit 4; }
command -v riscv64-unknown-elf-readelf >/dev/null || { echo "RISC-V readelf missing" >&2; exit 4; }
segments="$(riscv64-unknown-elf-readelf -lW "$elf")"
if grep -Eq 'LOAD.*RWE' <<< "$segments"; then
  echo "SECURITY FAILURE: BIOS contains writable + executable load segment" >&2
  exit 4
fi
grep -Eq 'LOAD.*R E ' <<< "$segments" || { echo "No RX BIOS code segment found" >&2; exit 4; }
grep -Eq 'LOAD.*RW ' <<< "$segments" || { echo "No RW BIOS data segment found" >&2; exit 4; }
echo "BIOS_ELF_NO_RWX=PASS"
echo "LiteX BIOS + Verilog/UCF generated at $out"
echo "NOTE: --generate does not run ISE, create a .bit file, or program an FPGA."
