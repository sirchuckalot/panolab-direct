# PanoLab Rescue v1 — Upstream Recovery Implementation Review

**Record:** PLR-RESEARCH-001 | **Date:** 2026-11-23 | **Status:** Reference selection; implementation and G2 hardware qualification pending  
**Normative contract:** [PanoLab Rescue v1](https://github.com/sirchuckalot/panolab-direct/blob/development/specs/PANOLAB_RESCUE_V1.md)

## Decision

There is **no verified off-the-shelf Pano G2 Rev B LiteX image with all PanoLab Rescue v1 features** among the sources inspected. Do not label any discovered artifact PanoLab Rescue-ready or deploy it unchanged.

Adopt **standard LiteX SoCCore/BIOS/firmware and the official `litex-boards` G2 platform as the implementation foundation**, use the historically hardware-booted `panog2_linux` image as **G2-specific LiteX evidence and bring-up comparison**, learn the failsafe bootloader model from **Foboot**, reuse the **BSP/host-update design approach** from **LimeSDR_GW**, and validate Ethernet boot/recovery behavior against **panog2_ldr** without incorporating its non-LiteX SoC. There is one runtime FPGA personality for Rescue and two application slots, not separate permanent bootstrap layers.

These are **source/adaptation decisions**, not bitstream acceptance. No source is being blindly copied; confirm SPDX/license and dependency compatibility for each file before porting.

## Upstream evidence register

| Source | Inspected revision | Published proof/artifact | Reuse boundary |
| --- | --- | --- | --- |
| [skiphansen/panog2_linux](https://github.com/skiphansen/panog2_linux) | `e66ecb97bddf2d83c06864f1ec59b864f8fd8c15` | Prebuilt `gateware-dvi.bin`, `gateware-hdmi.bin`; README includes real XC6SLX150 flash/BIOS/Linux/DHCP/ping logs | **G2 LiteX/DDR2/LiteEth/SPI proof, NOT a LiteX Rescue**, historic image installs via JTAG and Linux/rootfs use nearly the whole flash |
| [im-tomu/foboot](https://github.com/im-tomu/foboot) | `dfa09fc84b0acb4d9a2d409f3a381274a1551e9f` | Failsafe LiteX/VexRiscv+USB-DFU bootloader with separate firmware, shipped prebuilt multiboot/installable binaries and documented device enumeration/DFU operations | **Best directly functioning standalone LiteX recovery image design**; Fomu/iCE40/USB, **not G2/Spartan-6/Ethernet**. Top-level license Apache-2.0; review transitive license notices |
| [myriadrf/LimeSDR_GW](https://github.com/myriadrf/LimeSDR_GW) | `9899527b6a15ffdb4cb3b322512c541699564b06` | Cross-board LiteX soft-CPU firmware, FPGA flash commands, per-board BSP implementations, golden/user image code and documentation | **Firmware updater / common API / BSP precedent**; host links are USB/PCIe, not G2 Ethernet; documentation alone does not prove PanoLab A/B trial/confirm semantics |
| [skiphansen/panog2_ldr](https://github.com/skiphansen/panog2_ldr) | `423c163879f91229ede8b5923352b0b4bb3ae196` | Prebuilt G2 Rev B/C loader, documented stock-Ethernet installation, Telnet/TFTP flash/readback/boot, button/delayed recovery | **G2 physical recovery and migration reference; explicitly NOT LiteX**. FPGA top is Ultra-Embedded RISC-V/AXI SoC; firmware lwIP, GPL source. Do not make it our long-term second SoC |
| [litex-hub/litex-boards](https://github.com/litex-hub/litex-boards) | `2ccda1274d9a00088af3407bc93f0c7dd4892981` | `litex_boards/platforms/pano_logic_g2.py`, `litex_boards/targets/pano_logic_g2.py` with Rev B/C constraints, Ethernet and selectable CPU | **Upstream BSP foundation**, not a recovery implementation. Default CLI revision is `c`: always select G2 Rev B explicitly. Current stock target does not expose all needed Rescue SPI, flash journal or Spartan-6 ICAP features |
| [enjoy-digital/litex](https://github.com/enjoy-digital/litex) | `afed66238638fac1d1e13c3edd6568cdccea5356` | LiteX SoC/BIOS and documented TFTP, ROM/SPI/serial loading; software libraries and flash interfaces | **Common SoC/BIOS/software foundation**. Generic BIOS booting CPU software is not equivalent to FPGA MultiBoot/A/B firmware recovery |

### G2-specific locally uploaded artifact observation

The user-supplied `panog2_linux-master.zip` includes two prebuilt files, each 4,279,224 bytes (each rounds up to **17 × 256 KiB sectors**):

- `prebuilt/gateware-dvi.bin` SHA-256 `54d61ba59c0bbb9e3b4c0d7f72a2988fd1e63fa485b71d6edc0a148e1a40f2c8`
- `prebuilt/gateware-hdmi.bin` SHA-256 `1b2a7b434e77f2a1fb32c04193e25e6294ba6e297b963dd047d6c45eb253dfd9`

This is a **source artifact inspection**, not an independent boot on the owner's board. With 64 sectors in a 16 MiB Rev B, three 17-sector images require 51 sectors, leaving 13 sectors for all boot, identity, journal, alignment, and reserved regions. **This is only a plausibility estimate**; build actual Rescue/App images, account for SPI boot-header/fallback constraints and require Q01/Q02/Q04/Q05 proofs before selecting a permanent partition map. Do not adopt the Linux full-flash offsets.

## Architecture to implement

```text
Factory stock (migration only)
  -> manufacturer-compatible Ethernet update into a permitted image slot
  -> LiteX Rescue (independent bitstream + firmware in its ROM/BRAM)
     [CPU | PHY/LiteEth | TCP/IP | SPI read/erase/program/verify
      | board identity | durable journal | Spartan-6 ICAP/IPROG
      | profile-aware, bounded Ethernet management interface]
     -> trial APP_A or APP_B via FPGA reconfiguration
     <- application-triggered return if healthy
     <- independent power-cycle/button recovery if hung (must prove)
```

Foboot's *bootloader and firmware embedded into one configuration* is the reference for independently booting rescue without external Linux/rootfs. **Standard LiteX BIOS is the chosen recovery-firmware foundation**, rather than merely a source of boot/console/network primitives; PanoLab adds the network update service, A/B journal and FPGA-specific ICAP handoff. LimeSDR_GW's `firmware/main.c`, `firmware/bsp/`, flash drivers and host-command handling are a design reference, **not a drop-in Ethernet update server**. The independently working G2 `panog2_ldr` demonstrates the network provisioning path and button policy, **not a source that satisfies the LiteX requirement**.

## Required adaptations (not claimed done)

1. **Target-accurate BSP:** Rev B `XC6SLX150-2-FGG484`, actual SPI JEDEC geometry, 25-to-125 MHz PHY clock/reset sequencing, UART routing, board button and PHY initialization; pin the mutually compatible LiteX/Migen/LiteEth/LiteSPI source set and ISE tool versions. The historical G2 LiteEth workaround is not an accepted fix.
2. **True independently bootable Rescue:** CPU firmware linked into FPGA ROM/BRAM, no Linux or external boot payload for rescue readiness. Rescue must boot with an invalid/unavailable app slot and should not depend on DDR2 unless a separately demonstrated requirement forces it.
3. **Flash and reconfiguration:** Board-specific, bounded flash driver, programmed-image readback, Spartan-6 `ICAP_SPARTAN6` control and validated configuration/fallback headers. Do not assume 7-series ICAP glue works on Spartan-6.
4. **PanoLab v1 update semantics:** protected BOOT/RESCUE/IDENTITY, APP_A/APP_B, independent STATE_0/STATE_1, manifest target/hash/signature validation, staging to inactive slot, trial/confirm/revert journal with power-failure tests. Neither Foboot nor the historic G2 examples directly implements this full contract.
5. **Discovery/trust profile:** unique MAC and serial from board identity, DHCP/mDNS/DNS-SD, BIOS-based LiteEth networking, and the standard versioned management API. On an isolated owner-controlled LAN, `trusted-lan` intentionally permits unpaired bounded APP_A/B updates with a prominent warning; shared/production networks require authenticated access. Legacy factory protocol, Telnet and BIOS TFTP do not constitute a general unrestricted remote flash API.
6. **Independent emergency recovery:** prove cold boot goes to Rescue and a button/reset/power-cycle entry works if the app has configured successfully but hangs; pure ICAP return from the app does not cover this failure class.
7. **Two-board reproducibility:** deterministic pinning and builds, independent source verification, evidence from the owner's actual G2; hardware-qualified status only after PLR-ARCH-001 Q01–Q22 relevant tests pass.

## Adoption gates / candidate acceptance

| Gate | Proof | State |
| --- | --- | --- |
| R0 source vetting | Reference revisions, file-level licensing, artifact hashes, matching BSP | **Research complete at reference level; licensing audit pending** |
| R1 simulation | LiteX Rescue SoC boots firmware in simulation; mocked SPI and ICAP; watchdog/journal fault injection | Not run |
| R2 build | Pinned ISE 14.7 Spartan-6 implement/bitgen, timing, artifact report and image size | Not run |
| R3 actual G2 read-only | Rev B PHY/MAC, CPU BIOS, SPI JEDEC/identity, discovery; no programming | Not run |
| R4 isolated migration | Authorize exact board, stock entry-slot write, boot Rescue, demonstrate physical recovery | Not run |
| R5 A/B acceptance | Full Q01–Q22 BSP qualification including interrupted write, unhealthy app and two-board checks | Not run |

The newer [BIOS-first implementation plan](../docs/RESCUE_IMPLEMENTATION.md) and Rescue v1.1.0 revise the earlier all-authenticated network policy: Trusted-LAN unpaired operation is deliberately supported for isolated benches. This research record is an evidence review, not a physical qualification.

No physical board was flashed or claimed tested during this review. Do not write `main`. `development` is the only work branch; laptop local commit is pending reconciliation with published GitHub history. GitHub documentation changes must not be conflated with local hardware verification.

## Direct references

- [Pano G2 Linux published physical boot log and prebuilt images](https://github.com/skiphansen/panog2_linux/blob/e66ecb97bddf2d83c06864f1ec59b864f8fd8c15/README.md)
- [Foboot independently bootable bootloader and release artifacts](https://github.com/im-tomu/foboot/tree/dfa09fc84b0acb4d9a2d409f3a381274a1551e9f)
- [Foboot boot sequence](https://github.com/im-tomu/foboot/blob/dfa09fc84b0acb4d9a2d409f3a381274a1551e9f/doc/BOOT-SEQUENCE.md)
- [LimeSDR_GW firmware update/recovery](https://github.com/myriadrf/LimeSDR_GW/blob/9899527b6a15ffdb4cb3b322512c541699564b06/docs/docs/update_and_recovery.rst)
- [G2 independent network recovery README](https://github.com/skiphansen/panog2_ldr/blob/423c163879f91229ede8b5923352b0b4bb3ae196/README.md)
- [Official LiteX G2 target](https://github.com/litex-hub/litex-boards/blob/2ccda1274d9a00088af3407bc93f0c7dd4892981/litex_boards/targets/pano_logic_g2.py)