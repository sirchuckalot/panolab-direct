# PanoLab Rescue G2 Rev B — Source-first build and simulation evidence

**Record:** PLR-EVID-002 | **Date:** November 23, 2026 (Pacific) | **Status:** First SoC/Bios source milestone verified; NOT an accepted physical FPGA image.

**Related:** [First Rescue SoC](../boards/pano_g2_rev_b/README.md) · [Rescue v1.1.0](../specs/PANOLAB_RESCUE_V1.md) · [BIOS implementation direction](RESCUE_IMPLEMENTATION.md).

## What was actually executed

Environment: existing PanoLab rootless Docker development container, using only `/workspace/panolab-rescue-lab` disposable scratch files and rootless-local package locations. No changes to host packages, existing PanoLab services, live checkout, licenses or hardware. GitHub `main` remains frozen. Python 3.12, GNU Make, Icarus, Verilator and Yosys were available inside the container.

Selected source revisions were read from upstream GitHub on November 23 and cloned at their exact full Git commits. See [lock](../boards/pano_g2_rev_b/upstream.lock.json). Of particular relevance, this uses LiteX `afed66238638fac1d1e13c3edd6568cdccea5356`, LiteX-Boards `2ccda1274d9a00088af3407bc93f0c7dd4892981`, LiteEth `a54c730c323f271e5b5a33d48df54f6ce2d58c0a`, LiteSPI `a5a0090ad16c2bebe0cb01dcc07e843b558ca4f6`, Migen `e19524c963a8342952840983047557707fbe0b6a`.

The latest LiteX C runtime expected a newer Picolibc layout than the published PyPI `pythondata-software-picolibc 1.7.9.post181` wrapper provided. The workspace build explicitly redirected only its data location to pinned newer [LiteX Picolibc](https://github.com/litex-hub/picolibc/tree/16ff442da4b92e28d0753fabed18ad4a15254498), with no upstream C sources copied into the PanoLab repository. **Automating a clean, audited rootless dependency bootstrap remains pending.** This local workaround must not be silently assumed to reproduce on an arbitrary workstation.

## Evidence matrix

| ID | Check | Result and scope |
| --- | --- | --- |
| E01 | Pin five primary LiteX dependencies | PASS; exact full SHA Git checkouts |
| E02 | Source-level G2 Rev B SoC `finalize()` | PASS; correct `xc6slx150-2-fgg484` and VexRiscv; LiteEth and 16 MiB M25P128 LiteSPI instantiated |
| E03 | Recovery button synchronizer / held latch | PASS in Migen simulation; continuous hold, no hold, short pulse and late press; **not** real physical button qualification |
| E04 | Ethernet MAC guard | PASS; refuses missing/shared implicit lab MAC, multicast/non-LAA MAC, invalid DHCP/fixed-IP combination |
| E05 | Configurable boot-window input bounds | PASS; 1–60 seconds validated; **not** yet an executing firmware autoboot timer |
| E06 | Python test suite | PASS; **9 tests**, approximately 0.27 seconds in pinned workspace |
| E07 | BIOS software compile | PASS; VexRiscv RISC-V GCC toolchain; **39,156-byte `bios.bin`**, approx **38.23 KiB ROM**, **3.60 KiB SRAM** |
| E08 | Gateware generation | PASS; **492,579-byte generated Verilog** + **4,069-byte UCF** + CSR output; this is HDL, **not** a Spartan-6 `.bit` configuration file |
| E09 | Icarus generated-Verilog syntax | PASS with `-i` ignore-missing-blackboxes; **Xilinx primitives and VexRiscv are unresolved**, so not synthesis/timing proof |
| E10 | Live upstream LiteX BIOS simulation | PASS for **generic LiteX simulation platform**, not G2. VexRiscv executed, BIOS CRC passed, simulated SPI NOR initialized, prompt `litex>` appeared |
| E11 | Generic LiteX sim with Ethernet | Gateware, software and simulator binary compiled; execution BLOCKED because upstream TAP runner requires `sudo`, disallowed by rootless policy |
| E12 | ISE Spartan-6 synthesis/P&R/BitGen | NOT RUN; vendor toolchain approval/license and actual build not performed |
| E13 | G2 physical Ethernet, flash, button, ICAP, A/B | NOT RUN; no FPGA physically connected or programmed through this milestone |

### Reproducible final G2 source artifacts

Example: `PANOLAB_LAB_MAC=02:00:00:00:00:01` (explicit single-device **lab-only placeholder**, not persistent identity). Run the [build helper](../boards/pano_g2_rev_b/build_probe.sh) with pinned sources and workspace tools.

| Generated artifact | Exact size | SHA-256 |
| --- | ---: | --- |
| `software/bios/bios.bin` | 39,156 bytes | `52323e59edb6fe30c9b6d5d12b20be1ad7569eac2093217dacc4545db1d822a9` |
| `gateware/pano_logic_g2.v` | 492,579 bytes | `f113cc0f1e7ccbe26932cb1bca5328b27b3302f532da2fb5f9e6e1bb9ab8d92e` |
| `gateware/pano_logic_g2.ucf` | 4,069 bytes | Tool-generated constraint file; reviewed as an output, physical pinout not electrically validated |

Hashes identify **this particular workspace build**. Embedded timestamps, tool versions and generated metadata may affect byte-for-byte reproducibility; do not claim fully deterministic builds before a clean-room reproducibility check.

### Live BIOS simulation

The upstream `litex.tools.litex_sim` (Verilator, simulated SPI; no Ethernet TAP) started a VexRiscv at simulated 1 MHz and emitted:

```text
BIOS CRC passed (1a7b6d5e)
LiteX git sha1: afed6623
CPU: VexRiscv @ 1MHz
Initializing s25fl128l SPI Flash @0x01000000...
No boot medium found
litex>
```

The generic sim continued waiting in a console until terminated by an external 45-second timeout (exit code 124). **This is a successful live BIOS prompt observation, not a clean firmware exit**; the lack of a boot medium is expected. The simulated S25FL128L is **not** evidence the physical G2's M25P128 works.

A second attempt with simulated Ethernet successfully built its models and linked the simulator, but its `run_sim.sh` invoked `sudo` to set up a TAP interface; it did not reach a comparable session. We chose not to grant additional privileges. A future unprivileged socket-model or external test bridge is preferred.

## G2-specific source reuse and limitations

- **Taken from upstream LiteX-Boards:** Rev B pin assignments, FPGA part, UART routing, button signal, Marvell PHY/GMII pinout and Xilinx ISE target. No copy of the legacy Pano G2 HDL or stand-alone uploader is introduced.
- **Adaptation:** upstream generic G2 clock module couples Pano button to PLL reset, preventing button-held BIOS recovery; our `RescueClock` separates the button from FPGA reset, and `RescueButton` exports a synchronized/latching status to BIOS. **Actual 25/125 MHz PHY clock and cold-start operation remain untested.**
- **Model based on established upstream data:** `M25P128` SPI NOR and BIOS LiteSPI driver. Actual JEDEC geometry, erase protection and identity data are not yet read.
- **Research references only:** G2 factory multiboot header, golden/main slots, serial/MAC identity region; `panog2_ldr` demonstrates Ethernet update/button behavior but its non-LiteX SoC and firmware are **not adopted**.
- **Explicit incomplete features:** permanent identity reader, boot-state journal, BIOS autoboot decision path, `ICAP_SPARTAN6`, safe A/B update transaction, versioned network management endpoint, mDNS/DNS-SD and pairing/production security.

## Next acceptance gates

1. **BIOS policy and identity:** implement an upstream-compatible LiteX BIOS hook to read the actual unique MAC and boot journal, hold Rescue when button is latched, and start verified confirmed applications only after the bounded timeout.
2. **SPARTAN-6 configuration:** add `ICAP_SPARTAN6` glue with testbench and board-specific header/slot calculation; independently validate image sizes in ISE and failure/fallback semantics.
3. **Ethernet management:** reuse LiteEth/BIOS libraries to implement the bounded `trusted-lan` network API and later authenticated shared-lab profile; simulate network protocol without privileged TAP setup.
4. **Power-fail-safe flash and trial state:** implement inactive-slot update, readback verification, protected identity, journal and revert; failure-injection tests.
5. **Hardware acceptance:** after separate exact owner authorization, perform read-only real G2 BIOS/PHY/SPI/identity observation, independent button+power cycle recovery, then carefully staged write/provisioning. No remote agent or software success is permission to overwrite factory flash.

**Conclusion:** First source-first SoC and real LiteX BIOS build exist; the standardized Ethernet-recoverable FPGA appliance and physical `.bit` image **do not exist yet**. Claim hardware success only after vendor bitstream and G2 bench tests.
