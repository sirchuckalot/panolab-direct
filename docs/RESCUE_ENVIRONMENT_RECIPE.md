# PanoLab Rescue — Rootless LiteX Development Environment Recipe

**Record:** PLR-ENV-001 | **Date:** 2026-11-23 (US Pacific) | **Status:** Versioned Docker recipe; fresh isolated bootstrap + G2 BIOS source build validated; rebuilt full Docker image not yet accepted. The [unified development image and controlled migration](UNIFIED_DEV_IMAGE_UPGRADE.md) supersedes the original image-refresh note and provides the explicit owner-laptop upgrade command.

**Source of truth:** [modern Dockerfile](../docker/modern/Dockerfile), [bootstrap utility](../docker/modern/litex-bootstrap.py), [upstream lock](../docker/modern/litex-upstream.lock.json), [Python package pins](../docker/modern/litex-requirements.txt), [rootless installer](../host/rootless-install.sh). The identical [G2 reference lock](../boards/pano_g2_rev_b/upstream.lock.json) is checked by [offline unit tests](../tests/test_litex_recipe.py).

## What a newly built tools image contains

Ubuntu 24.04, Python 3.12, HDL tools (Yosys, Icarus, Verilator), Git, Make/GCC/G++, Codex CLI and code-mode host (existing checksummed installer), plus:

| Layer | Packages/sources | Purpose |
| --- | --- | --- |
| OS build tools | `gcc-riscv64-unknown-elf`, `binutils-riscv64-unknown-elf` | Compile the VexRiscv LiteX BIOS (no host compiler install) |
| Native simulation libraries | `libevent-dev`, `libjson-c-dev`, `zlib1g-dev`, `pkg-config` | Compile LiteX Verilator network simulation modules |
| LiteX source tree | Pinned Git checkouts of LiteX/BIOS, LiteX-Boards, LiteEth, LiteSPI, Migen | Established, reusable FPGA SoC framework and Rev B pinout/clock/PHY target |
| CPU and runtime | `pythondata-cpu-vexriscv`, `pythondata-software-compiler-rt`, upstream pinned Picolibc and its Pythondata wrapper | Existing RISC-V HDL and BIOS C runtime |
| Python/firmware tools | Pinned virtualenv packages including `meson`, `ninja`, `pyserial`, `packaging`, `PyYAML`, `requests`, `jsonschema`, `pythondata-misc-tapcfg` | BIOS build, tooling, simulator support |

The full pinned revisions and installed Python package versions are committed rather than silently installing whatever a `master` branch or latest PyPI resolves to. The environment lives at **`/opt/panolab/litex`** inside a *new* development image, with `/opt/panolab/litex/env.sh` exporting the source and virtualenv paths. The installed runtime does not require GitHub access to run; network is needed **while building** the image to fetch public pinned source and package dependencies.

This is a development image, **not** an FPGA firmware image or standalone G2 firmware flasher. No Xilinx ISE license, Xilinx private installer, user credential or factory firmware is baked into it. ISE remains a separate licensed build worker. The Docker build executes as container-root under the owner's rootless Docker engine, never host root.

## Problems encountered and their corrections

| Encountered in real trial | Root cause | Permanent recipe change |
| --- | --- | --- |
| `pythondata-cpu-vexriscv module not installed` | Bare HDL development image had no LiteX dependencies | Install pinned VexRiscv data and clone exact upstream Git revisions |
| No `riscv64-unknown-elf-gcc` | HDL tools alone cannot compile the BIOS | Add Ubuntu RISC-V cross-toolchain packages |
| `pythondata-software-picolibc` could not locate `libc/stdio/printf.c` | Older PyPI 1.7.9 wrapper shipped a layout incompatible with pinned 2026 LiteX BIOS source | Clone the newer pinned LiteX Picolibc data and matching Pythondata wrapper; do not install the old PyPI wrapper |
| `No space left on device` building the Picolibc Python wheel | Packaging the large source submodule in the container's temporary area | Avoid the oversized Python wheel and use pinned Git source; isolate pip temporary files under the recipe prefix |
| Clean build still failed despite valid Picolibc import | A relative `data` symlink was copied by LiteX to another directory, breaking its target | The recipe creates and verifies an **absolute link within the container**; normal LiteX source-copy keeps it valid |
| Meson/Ninja unavailable on `PATH` | `pip --target` did not provide their executable launchers | Use an isolated Python virtualenv with `bin` on `PATH`; test both commands |
| Verilator Ethernet model compilation failed on `event2/listener.h` and `json-c/json.h` | Missing C development headers/libraries | Install `libevent-dev`, `libjson-c-dev`, `zlib1g-dev` |
| LiteX TAP-network simulator invoked `sudo` | Upstream Ethernet simulation's TAP setup assumes elevated networking privileges | **Still blocked by design.** Do not grant privileges or run `sudo`; use unprivileged BIOS/SPI simulation and design a socket-based Ethernet test next |
| Official G2 target rejected DHCP + fixed IP; holding Pano button also resets PLL | Upstream generic board target behavior unsuitable for Rescue-first, button-held boot | Addressed in the separate [G2 Rescue SoC](../boards/pano_g2_rev_b/rescue_soc.py), not by forking upstream LiteX |
| Existing dev image tag already present, so future installer would not rebuild | Old installer tested only image existence | Installer now tests a versioned image label and builds a new image if stale; **does not automatically replace a running dev container** |

## Reproducible rootless usage

From the laptop's **owner account** after reconciling its local `development` checkout with GitHub (never force-pull over another history):

```sh
bash ./panolab-install.sh --check  # read-only preflight
bash ./panolab-install.sh          # rootless build/install when authorized
```

On a newly created PanoLab development container, with project repository mounted read-only as specified by the rootless installer:

```sh
. /opt/panolab/litex/env.sh
python3 /opt/panolab/recipes/litex-bootstrap.py \
  --prefix /opt/panolab/litex \
  --lock /opt/panolab/recipes/litex-upstream.lock.json \
  --requirements /opt/panolab/recipes/litex-requirements.txt --verify-only

export PANOLAB_LAB_MAC=02:00:00:00:00:01 # one isolated lab unit only
bash /repo/boards/pano_g2_rev_b/build_probe.sh
python3 /repo/boards/pano_g2_rev_b/test_rescue_soc.py
```

Use the proper checkout paths if mounted elsewhere; the read-only `/repo/boards` path above is the installer default. `build_probe.sh` checks all pinned upstream Git SHAs and compiles LiteX BIOS + generates Verilog/UCF but **never calls ISE or flashes hardware**. Use a unique lab MAC per board; this is not yet a permanent identity implementation.

**Existing-container migration policy:** An ordinary `--install` rebuilds the same modern tools image without replacing the running dev. The additional **explicit** `--upgrade-dev` mode performs [the guarded, rollback-capable dev-only replacement](UNIFIED_DEV_IMAGE_UPGRADE.md) after validating all mounts, source revisions and the new image. It retains the previous dev stopped for verification and never restarts manager/ISE/tunnel.

## Verification completed

In the existing rootless development container, from a fresh source and virtualenv prefix rather than reusing the previous LiteX installation:

- Seven Git repositories checked out and verified at the exact revisions in the lock (including the Picolibc wrapper and data).
- Pinned Python dependencies installed, Meson/Ninja available, `pip check` clean, LiteX imports and SPI flash geometry sanity checked.
- The updated G2 `build_probe.sh` generated an actual VexRiscv LiteX BIOS binary (**39,156 bytes, 38.23 KiB ROM, 3.60 KiB SRAM**) and a G2 Rev B Verilog netlist (**492,579 bytes**) plus Xilinx UCF and CSR metadata.
- The existing nine G2 source/simulation tests passed, and Icarus parsed the generated Verilog using black boxes for Xilinx and VexRiscv primitives.
- The upstream generic LiteX live Verilator BIOS/SPI simulation had already reached the `litex>` prompt. The restricted rootless network simulator is **not** claimed to run over Ethernet.

**Not yet verified:** an actual rebuilt Docker image using this committed Dockerfile on the laptop's rootless Docker engine; a clean GitHub runner build; Spartan-6 ISE placement/routing/bitstream; physical Pano G2 boot, PHY, button/recovery, or Ethernet A/B updater. A valid source/BIOS build must not be represented as proven FPGA hardware.

## Drift prevention and qualification

The offline `tests/test_litex_recipe.py` compares the board and Docker upstream locks, checks the exact Python pins, Dockerfile deps/image marker, rootless installer non-destructive behavior, and rejects verify-only requests against an unprovisioned prefix. The image build itself runs the bootstrap and a read-only-friendly verification pass, making upstream mismatch a **build failure** rather than a hidden runtime surprise. If any version is advanced, update both locks, the image marker and the verified evidence together.

**Safety:** no sudo/host apt, no rootful Docker daemon, no destructive image/container prune, no mounted secrets in the image, no generic SPI flashing, no automatic FPGA programming, and no alteration of `main`.
