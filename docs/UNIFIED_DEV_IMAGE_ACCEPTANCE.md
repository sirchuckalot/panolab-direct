# Unified Modern FPGA Development Image — Laptop Acceptance Evidence

**Record:** PLR-ENV-003 | **Evidence date:** 2026-11-24 UTC / 2026-11-23 US Pacific | **Status:** **LAPTOP_VERIFIED** for the unified *software development environment*; **not** a physical FPGA or ISE acceptance.

**Implementation source:** [Unified environment recipe](UNIFIED_DEV_IMAGE_UPGRADE.md), [Dockerfile](../docker/modern/Dockerfile), [rootless migration](../host/upgrade-dev-image.sh). **Installation commit:** `27c0122d0edb13a5118f254f4c0a705a6da854ad` (`development`). **Accepted baseline `main`:** `006b6ee608c5c496292686e2f8c1f690aaa158f2`, unchanged.

## Owner execution and independent live verification

The owner executed the approved commit-pinned, single-command source-sync and `--upgrade-dev` procedure on the laptop. Their terminal transcript showed:

- GitHub `origin/development` advanced to `27c0122`; the canonical laptop checkout's **old local commit** `f1ca3a66` was proved tree-equivalent to the known GitHub historical milestone and preserved in `panolab/backup-development-f1ca3a66` before advancing the clean checkout. `SOURCE_UPDATE=PASS`.
- The **existing** `panolab-direct-modern:local` Ubuntu 24.04 development image was rebuilt using its seven-section Dockerfile (no additional dedicated LiteX image). Required Ubuntu HDL and RISC-V packages installed; both Codex 0.171.0 downloads passed their SHA-256 checks.
- Seven upstream Git source pins matched; Picolibc wrapper and data location, pinned Python versions, `pip check`, Meson and Ninja passed. `LITEX_REQUIRED_TOOLS=PASS` and `LITEX_IMAGE_RECIPE_READY=/opt/panolab/litex`.
- Built image and running container image ID: `sha256:c5799cd625d42ff4bd8158767a0917a5cda18082e2dc1976869400c93b5b1479`. Image smoke tests completed in a **network-disabled, read-only** one-shot container before the dev swap.
- `panolab-direct-dev-1` was replaced with the **same** dev name, owner bind mounts, CPU/memory/PID limits and private Codex mount. `DEV_UPGRADE_RESULT=PASS`.
- Previous dev container retained stopped: `panolab-direct-dev-1-rollback-20261124T020818Z`. Remote status subsequently showed `Exited (137)`; that exit status should not be described as a graceful stop. The rollback object is preserved; it has **not been removed**.
- All six named PanoLab active services remained running; their management/tunnel processes did not undergo the dev container replacement.
- A read-only PanoLab MCP check verified the laptop checkout is clean on `development` at exactly `27c0122d0edb13a5118f254f4c0a705a6da854ad`.

This was followed by **independent live MCP checks** against the replacement dev, beyond merely trusting the pasted installer transcript.

## Live test matrix

**Regression summary: 23/23 tests passed** (11 environment/recipe contracts, 3 disposable-Git migration tests, and 9 G2 SoC tests), in addition to source-pin, live BIOS, artifact and service acceptance checks.

| Test | Evidence / result |
| --- | --- |
| Runtime services | **PASS:** `panolab-direct-dev-1`, tunnel, manager, repo-git, Docker broker and setup all `Up` |
| Modern toolchain | **PASS:** Python 3.12.3, RISC-V GCC 13.2.0, Yosys 0.33, Icarus 12.0, Verilator 5.020, Meson 1.12.1, Ninja 1.13.2, Codex CLI 0.171.0 |
| LiteX source integrity | **PASS:** all seven locked upstream SHA-1 Git commits match their deployed checkouts |
| Picolibc/SPI/virtualenv | **PASS:** LiteX runtime imports, 16 MiB LiteSPI NOR model, Picolibc source file, exact pinned Python packages, `pip check` |
| CPU/memory/process caps | **PASS:** cgroup `cpu.max=200000 100000`, `memory.max=4294967296`, `pids.max=256` |
| Workspace/source boundaries | **PASS:** project and persistent workspace readable; `/repo/docker/private` absent |
| Codex account | **PASS:** owner's terminal showed existing login recognized; no authentication material displayed or committed |
| Recipe contracts | **11/11 PASS** inside the new laptop container |
| Git-history reconciliation | **3/3 PASS** using disposable local fixture repos, with no real checkout modifications |
| G2 source/RTL/button simulation | **9/9 PASS** inside the new dev container |
| Generated BIOS | **PASS:** `bios.bin` 39,156 bytes; SHA-256 `8f9b16abc01f2d789cf7d190df97b690429d3b2d8032383417444d5b210399d3` |
| Generated G2 HDL | **PASS:** `pano_logic_g2.v` 492,579 bytes; SHA-256 `1461a0e5c9e6a33ef83ae6976b4ed7034e84bfabc080fb0fc9ee8e06f767cf09` |
| Rev B constraints | **PASS (generation only):** `pano_logic_g2.ucf` 4,069 bytes |
| Icarus Verilog parser | **PASS:** `iverilog -g2012 -i -tnull -s pano_logic_g2` on generated HDL, with unresolved vendor/CPU primitives ignored; this is **not synthesis** |
| Live generic LiteX simulation | **PASS:** actual VexRiscv BIOS ran, `BIOS CRC passed (7c83c0ea)`, simulated `s25fl128l` SPI flash initialized, boot media absent as expected, interactive `litex>` console observed |
| Generic simulator process exit | **EXPECTED TIMEOUT:** bounded `timeout 85s` stopped an interactive console waiting for input (exit 124); startup proof is positive, not a clean firmware shutdown |
| Physical G2, ISE, Ethernet rescue | **NOT TESTED:** separate qualification gates |

The generated G2 artifacts remain on the owner's existing persistent workspace at `/workspace/panolab-rescue-upgrade-20261124T020839Z`. The live generic simulation log is `/workspace/panolab-rescue-live-sim-20261124/sim.log`; its generated simulation is **generic LiteX**, **not** a complete FPGA-accurate G2 model. No SPI flash device was written.

## Subsequent toolchain cleanup

After this first-image acceptance, a separate [clean-up milestone](DEV_TOOLCHAIN_WARNING_CLEANUP.md) implements Buildx host-side provisioning and exact rollback-container removal as a guarded owner action, and verifies a warning-free G2 BIOS source build with RX/RW load segments. This record's warning and rollback details below remain historical evidence of the earlier acceptance. Host cleanup is **pending** until the owner executes the new operation; do not describe it as already completed.

## Observed non-blocking issues

1. Docker reported a deprecated legacy image builder and suggested Buildx. The builder **succeeded**; future BuildKit/Buildx adoption should be planned inside the existing rootless tooling, not by proliferating images or changing the host without review.
2. Upstream C compilation emitted warnings about prototypes/unused functions, and the bare-metal `bios.elf` linker reported a RWX load segment. These are **not environment-build failures**; review memory/linker protections in the BIOS hardening phase before using images in production.
3. The old rollback container shows exit code 137. Its preserved status is not evidence of data loss, but the precise termination cause has not been qualified. Do not prune the backup without separate owner approval.
4. `litex_sim` uses ANSI-colored terminal output; a literal raw-text `grep 'litex>'` missed the prompt in an initial diagnostic. Stripping ANSI escapes confirmed the console output and yielded `GENERIC_LITEX_BIOS_CONSOLE=PASS`.

## Decision and remaining gates

**Acceptance:** The **single unified modern development image is accepted as the working laptop-local software toolchain**. It replaces the older development container **without creating another long-lived development service**. The installation and regression procedures are now supported by end-to-end laptop evidence.

**Still pending:** vendor ISE 14.7 synthesis/place-route/BitGen, physically demonstrated Pano G2 Rev B clock/reset, Ethernet PHY and SPI JEDEC/identity readings, independent power-cycle/button recovery, production boot journal/ICAP/A-B management, and a rootless unprivileged Ethernet simulation bridge. Do not equate compiled BIOS, generated HDL or simulated SPI with a flashable, hardware-qualified Rescue image.

**Preservation:** Keep the prior stopped development container and historical Git backup ref until the owner approves cleanup. No `docker system prune`, host package installation, rootful operations or FPGA programming took place through these tests.
