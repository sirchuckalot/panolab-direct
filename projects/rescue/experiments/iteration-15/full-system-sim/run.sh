#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
stage=/workspace/ise-staging/rescue_g2b_network_diag
printf '%s\n' 'c15617b49fb1a05a4e60db2516016c17e54a20f7b5e6773a942a092f2c6afcb7  pano_logic_g2.v' '10a97e84013b214c9fb480e594e438f8b1b5b76121a2545cb6489c7e29679f76  VexRiscv.v' | (cd "$stage"; sha256sum -c -)
python3 packet_fixture.py
TMPDIR="$PWD" verilator --binary --timing -j 4 -Wno-fatal --top-module tb --Mdir obj_dir primitives.sv tb.sv "$stage/pano_logic_g2.v" "$stage/VexRiscv.v" > run-build.log 2>&1
timeout 100 stdbuf -oL obj_dir/Vtb +ms=100 > run-unknown.log 2>&1
grep -F 'JEDEC probe failed (6)' run-unknown.log
grep -F 'policy returned RECOVERY ONLY' run-unknown.log
timeout 100 stdbuf -oL obj_dir/Vtb +ms=100 +known_flash +button > run-held.log 2>&1
grep -F 'JEDEC 202018 capacity 16777216 erase 262144 page 256' run-held.log
grep -F 'startup button held' run-held.log
timeout 100 stdbuf -oL obj_dir/Vtb +ms=550 +known_flash +network > run-network.log 2>&1
grep -F 'BIOS CRC passed' run-network.log
grep -F 'startup button released' run-network.log
grep -F 'UART console ready' run-network.log
PYTHONDONTWRITEBYTECODE=1 python3 verify_packet.py | tee run-network-verification.log
