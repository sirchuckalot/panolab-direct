#!/usr/bin/env python3
from pathlib import Path
import re, subprocess, sys, hashlib
p=Path(sys.argv[1]); expected=int(sys.argv[2]); elf=p/'software/bios/bios.elf'; binary=p/'software/bios/bios.bin'; gate=p/'gateware/pano_logic_g2.v'; cfg=(p/'software/include/generated/soc.h').read_text(); log=(p/'build.log').read_text()
assert re.search(r'^#define PANOLAB_AUTOBOOT_WINDOW_S '+str(expected)+r'$',cfg,re.M)
assert re.search(r'^#define CONFIG_BIOS_NO_BOOT\s*$',cfg,re.M)
assert not re.search(r'warning:|error:',log,re.I), 'build diagnostics'
assert 0<binary.stat().st_size<=65536 and gate.stat().st_size>0
nm=subprocess.check_output(['riscv64-unknown-elf-nm',str(elf)],text=True); syms={l.split()[-1] for l in nm.splitlines() if l.split()}
assert {'rescue_boot_step','rescue_bios_diagnose','rescue_flash_probe','rescue_flash_probe_litex','rescue_geometry_lookup','command_dispatcher','readline'}<=syms
assert not {'boot_sequence','serialboot','netboot','flashboot','romboot','eth_init','net_init','spiflash_init'}&syms
headers=subprocess.check_output(['riscv64-unknown-elf-readelf','-lW',str(elf)],text=True); loads=[l for l in headers.splitlines() if re.match(r'\s*LOAD\b',l)]; assert loads and any(re.search(r'\bR E\b',l) for l in loads) and any(re.search(r'\bRW\b',l) for l in loads) and not any('RWE' in l for l in loads)
ucf=(p/'gateware/pano_logic_g2.ucf').read_bytes(); base=Path(__file__).resolve().parent.parent/'timing-fix/build/gateware/pano_logic_g2.ucf'; assert ucf==base.read_bytes()
print(f'PASS: diagnostic firmware {expected}s, compiled policy, no stock autoboot or network/flash initialization, UART console, RX/RW, no compiler diagnostics, matching UCF')
for f in (binary,elf,gate): print(f'{f.name}: {f.stat().st_size} bytes SHA256={hashlib.sha256(f.read_bytes()).hexdigest()}')
