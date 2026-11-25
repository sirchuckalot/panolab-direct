# PanoLab Rescue — LiteX BIOS-Based Implementation Plan

**Record:** PLR-IMPL-001 | **Date:** 2026-11-23 | **Status:** Implementation underway: [first G2 Rev B LiteX SoC](../projects/rescue/README.md) and [verification record](RESCUE_BUILD_EVIDENCE.md) published; full recovery functionality and physical hardware qualification pending
**Normative:** [PanoLab Rescue v1](../specs/PANOLAB_RESCUE_V1.md)  
**Source research:** [Upstream implementation review](../specs/PANOLAB_RESCUE_UPSTREAM_ADOPTION_REVIEW.md)

## Product objective

A developer plugs a supported FPGA appliance into their own Ethernet network, holds its recovery button at power-on when maintenance is desired, discovers it, and uploads/validates/runs FPGA images from a laptop. Otherwise, the independently bootable Rescue environment starts and after a short **configurable autoboot window** loads the last confirmed application. This is the same developer experience on every qualified BSP. Neither an attached serial console nor JTAG is required for normal development, updates, or recovery. JTAG remains a last-resort means of repairing corrupted boot flash or broken hardware.

**Rescue and applications are mutually exclusive FPGA configurations, not simultaneous processes.** The CPU in Rescue is absent after ICAP loads the application. A truly hung application may require power cycling while the physical recovery button is held; absent an independent hardware watchdog, the app itself cannot guarantee recovery.

## Reuse upstream LiteX BIOS

**Choose the existing LiteX boot path, not a homegrown boot ROM.** Build a G2 Rev B SoCCore with VexRiscv, an embedded LiteX BIOS firmware image in ROM/BRAM, LiteEth and SPI flash access. Reuse the upstream BIOS console/diagnostics, initialization, boot-method registration, TFTP/network and LiteSPI drivers. Treat the published G2 LiteX/Linux BIOS boot log as hardware evidence, not as a complete PanoLab recovery binary.

| Upstream LiteX / existing proof | PanoLab-specific extension |
| --- | --- |
| LiteX SoC and LiteX BIOS | Rescue boot policy and standard device identity/status |
| LiteEth, PHY and BIOS network routines | DNS-SD/mDNS and a constrained, versioned Ethernet management endpoint |
| LiteSPI + BIOS SPI drivers | Erase-bounded, readback-verified, partition-scoped image updates |
| BIOS command/boot-method registration | Hold Rescue, stage, verify, trial, confirm, rollback |
| Official G2 platform/constraints | Button sampling, Spartan-6 ICAP/IPROG, boot header and golden fallback validation |
| Foboot failsafe model, panog2_ldr G2 network recovery | Transaction journal and PanoLab A/B qualification |

BIOS `flashboot` normally boots **CPU software**, and `netboot` loads **CPU software** over TFTP. Neither operation by itself changes the FPGA configuration. The BSP supplies a distinct `reconfigure(slot)` operation using the FPGA family’s multiboot mechanism. For G2 this requires `ICAP_SPARTAN6`, not the newer `ICAPE2` primitive.

The BIOS's raw flash/memory commands can remain accessible for optional, physically controlled serial debugging, but must NOT be offered as unrestricted network commands. PanoLab's Ethernet API invokes the same underlying drivers through bounded slot-specific transactions. BIOS TFTP is an initial reusable transfer primitive, not a complete versioned update/identity service; an on-board management server remains to be implemented and measured for resource use. No Linux image or DDR2 boot payload is required for Rescue itself.

## Boot state and physical interaction

```text
POWER-ON / HARD RESET
        |
        v
RESCUE FPGA configuration (boot source and fallback BSP-proven)
        |
        v
LiteX BIOS / SPI identity / redundant boot journal
        |
        +-- Pano button HELD during defined startup sample --> RESCUE_HELD
        |                                                     stay on Ethernet
        |                                                     until explicit boot
        |
        +-- no valid confirmed image / unsafe boot state ----> RESCUE_IDLE
        |
        +-- previous trial failed/unconfirmed ----------------> ROLLBACK / RESCUE
        |
        +-- healthy confirmed image --------------------------> AUTOBOOT_WINDOW
                                                                    |
                                                 hold-rescue command if ready
                                                                    |
                                                 timer expires, verify image
                                                                    |
                                                   ICAP -> application A or B
```

1. **Cold boot Rescue first** is a hardware requirement, **not yet demonstrated on the G2**. Boot headers, flash slots and fallback must be proven before replacing factory boot regions.
2. Holding the Pano's **active-low button** while powering on MUST suppress autoboot. Sample/debounce at a BSP-defined stage that works across the G2 PHY 25-MHz-to-125-MHz clock transition. A held button means remain indefinitely in Ethernet Rescue, not immediately flash.
3. With no held button and a confirmed valid app, Rescue waits through a **proposed five-second default window** (adjustable, bounded; actual value pending hardware proof) then boots the confirmed slot. No link/DHCP MUST NOT indefinitely stall autoboot; invalid app MUST NOT boot. Without a confirmed application, stay in Rescue.
4. Within the window a network request can *optionally* cancel autoboot if IP is already available. It is NOT the guaranteed escape path; the button is. Once explicitly held in Rescue, only an explicit boot action leaves Rescue.
5. After the application takes over, Rescue's DNS-SD service and management endpoint disappear. A compatible application can expose its own interface or a simple return-to-Rescue ICAP shim. For a failed app, physical button + power cycle must restore Rescue. Hardware independent watchdog recovery is optional until proven.

## Ethernet developer experience

| Operation | Available via network while Rescue runs? |
| --- | --- |
| Discover / identify / status / read MAC & serial | Yes |
| Read/backup authorized SPI data regions | Yes, with bounded export |
| Stage and verify FPGA app image into inactive A/B | Yes |
| Trial boot, confirm, rollback, choose confirmed app | Yes |
| Cold-boot recovery button selection | Physical input, then all Rescue controls available over Ethernet |
| Rescue or BOOT-region maintenance | Via a *separate, explicitly enabled* network maintenance transaction only after independent fallback is proven |
| Raw arbitrary flash/CSR/JTAG commands | No ordinary remote endpoint |

**Illustrative CLI only; not implemented:**

```console
panolab discover
panolab status <device-id>
panolab backup <device-id> --region identity
panolab update <device-id> new-image.pano --slot inactive
panolab verify <device-id>
panolab boot <device-id> --trial
panolab confirm <device-id> --trial <trial-id>
panolab rollback <device-id>
```

Normal application staging never overwrites `BOOT`, `RESCUE`, `IDENTITY` or the current confirmed image. Validate FPGA target, board revision, bitstream size, the manifest, digest, write-readback and journal before trial boot. A valid FPGA configuration does not prove health; host-observed tests and trial ID confirmation are required. Network Rescue is unavailable while an application is running, so a healthy app uses return-to-Rescue or a documented reset; an unresponsive app requires the tested physical path. A CLI request made while only the application is present must not pretend it contacted Rescue.

## Accessible developer trust profile

The **default first-use mode is `trusted-lan` (unpaired)**, only for an isolated, owner-controlled Ethernet development network. No password, certificate, cloud account or pairing is required to issue the documented *bounded* network application-update and boot commands. Any machine able to reach the service can issue those permitted commands. This is an explicit trusted-network assumption, **not sender authentication**. The Pano button selects whether Rescue stays active; it does not prove which laptop is sending packets.

Device discovery and status MUST label `mode=rescue`, `profile=trusted-lan` and `paired=false`, with an unpaired warning in host tooling. Do not expose this mode to guest Wi-Fi, a shared office network or the internet. In a lab that is not fully controlled, use a paired `developer` profile; `production` also requires protected encrypted transport and signed/authorized updates. Both use the same PanoLab API and boot lifecycle. HTTP over the isolated LAN is permitted for the unpaired profile; paired/production must authenticate clients and prevent replays, with production encrypted.

**Reliability protections are not optional security features:** partition bounds, protected identity and recovery, readback verification, A/B last-known-good preservation, image/manifest checks and idempotent journaled updates apply even in unpaired mode. Network Rescue updates are possible only in a separate maintenance operation with independent fallback proof. Do not provide a remote generic erase/write-address command.

**This device policy does not loosen the laptop MCP policy:** an AI agent/remote manager still requires exact owner approval for physical write operations; an unpaired device on a trusted LAN is not blanket consent for automated flashing.

## G2 Rev B BSP specifics and evidence gates

Target: **XC6SLX150-2-FGG484**, nominal 16 MiB external SPI NOR and Rev B-specific PHY reset/clock pins. SPI JEDEC/erase layout must be read from real hardware. Published G2 LiteX bitstreams are ~4.28 MiB; three 17-sector-aligned FPGA images are *plausible* in 16 MiB but do not prove BOOT, identity, journal, metadata and fallback fit. Derive offsets from built images and configuration requirements, not factory-layout guesses. A single common LiteX **source implementation** can support many BSPs; binaries still target a specific FPGA/board compatibility group.

| Milestone | Required evidence (no unearned PASS) |
| --- | --- |
| B0: Source selection | Pin mutually compatible LiteX, Migen, LiteEth, LiteSPI and G2 target revisions; license review |
| B1: BIOS boot simulation | Embedded BIOS boots independently; mock SPI, button-held / timeout and invalid-app behavior |
| B2: Vendor FPGA build | Separately authorized ISE 14.7 synthesis, P&R/timing, actual image sizes and valid protected slot map |
| B3: Read-only device | Explicitly authorized Rev B BIOS startup, SPI JEDEC/identity and Ethernet discovery |
| B4: Recovery | Physically prove cold-boot Rescue, button-held no-autoboot and return after broken user image |
| B5: Network flash | Explicitly authorized bounded A/B upload/verify/trial/rollback; forced interruption / journal tests |
| B6: Trust profiles | Unpaired trusted-lan works and is clearly marked; protected regions stay unreachable; paired/production deny anonymous access |
| B7: Multi-board BSP | Same manifest, CLI and update lifecycle operate on another physically qualified board |

Current checkpoint: the source/BIOS generation portion of B1 and the diagnostic vendor implementation/timing portion of B2 have passed for named candidates. B2's actual protected slot map and B3–B7 physical and integration requirements remain open. The [iteration-15 checkpoint](../projects/rescue/experiments/iteration-15/README.md) records separate native, RTL, CPU/GMII and vendor evidence; the [stock research](../research/pano-stock/README.md) records real stock access, not Rescue qualification. Implementation changes go on `development` only; `main` remains the accepted baseline.

## Upstream source pointers

- [LiteX BIOS main](https://github.com/enjoy-digital/litex/blob/master/litex/soc/software/bios/main.c)
- [LiteX BIOS boot.c](https://github.com/enjoy-digital/litex/blob/master/litex/soc/software/bios/boot.c)
- [LiteX BIOS SPI flash commands](https://github.com/enjoy-digital/litex/blob/master/litex/soc/software/bios/cmds/cmd_spiflash.c)
- [Official G2 LiteX target](https://github.com/litex-hub/litex-boards/blob/master/litex_boards/targets/pano_logic_g2.py)
- [Pano G2 LiteX/Linux boot evidence](https://github.com/skiphansen/panog2_linux)
- [G2 Ethernet loader and button recovery](https://github.com/skiphansen/panog2_ldr)
