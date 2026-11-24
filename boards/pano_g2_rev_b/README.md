# PanoLab Rescue — Pano Logic G2 Rev B reference SoC (first implementation)

**Status: source elaboration and BIOS generation verified; not a flashable hardware-qualified image.**  
**Contract:** [Rescue v1.1.0](../../specs/PANOLAB_RESCUE_V1.md) · [Implementation plan](../../docs/RESCUE_IMPLEMENTATION.md) · [Evidence](../../docs/RESCUE_BUILD_EVIDENCE.md)

This is the initial PanoLab Rescue LiteX SoC, **not a fork of panog2_ldr** or an alternative FPGA bootloader. It directly imports current pinned LiteX, LiteX-Boards, LiteEth, LiteSPI and Migen. The only board-specific logic here is the Rev B clock/reset adaptation and a synchronized/latching recovery-button CSR. It compiles the established LiteX BIOS with [source-hash-guarded, build-output-only compatibility fixes](bios_source_overlay.py). The original LiteX/Migen/LiteEth/LiteSPI and Pythondata installation files remain **unmodified**.

## Included and tested

- Board selection is **explicitly Rev B**, Spartan-6 XC6SLX150-2-FGG484, using the upstream G2 platform (clocks/pinout, SPI, Ethernet, button) and ISE build target.
- VexRiscv, ROM + SRAM, standard LiteX BIOS, LiteEth Ethernet MAC + G2 PHY, LiteSPI M25P128 model, CSR diagnostic/status registers.
- Reset/clock workaround: upstream generic target gates PLL reset on Pano button; Rescue instead uses the declared board reset input so it can *observe* a button held at power-on. Real clock/PHY/reset power sequencing **must** be checked on the G2.
- A synchronized, startup-window recovery-button latch; **this does not yet implement boot timeout or ICAP reconfiguration**. A bounded autoboot-seconds configuration constant is exported for the future BIOS policy hook.
- Ethernet-enabled builds require an explicit, locally administered **unique lab MAC**. Stock BIOS otherwise has a shared fallback address. The proper read-from-persistent-identity MAC driver remains to implement before multi-board deployment.

The target refuses a shared implicit MAC and rejects out-of-range or multicast/non-local lab MACs. A lab MAC is **for source/build/simulation proof only**, not a substitute for extracted stock board identity.

## Reproduce in the rootless development container

The rootless [modern tools image](../../docker/modern/Dockerfile) now provisions pinned upstream source, an isolated Python virtual environment, the RISC-V BIOS toolchain, and simulation libraries. Source its environment file inside a **newly built** PanoLab development image. See the [environment recipe](../../docs/RESCUE_ENVIRONMENT_RECIPE.md) for installation and existing-container migration. The helper verifies all **seven** upstream source revisions and requires no host packages or `sudo`.

```sh
. /opt/panolab/litex/env.sh  # inside a newly built development container
export PANOLAB_LAB_MAC=02:00:00:00:00:01  # for a single isolated lab build only
./boards/pano_g2_rev_b/build_probe.sh
```

Direct source verification after dependencies are present:

```sh
python3 boards/pano_g2_rev_b/test_rescue_soc.py
```

Outputs are BIOS `bios.bin`, generated LiteX Verilog, UCF and CSR JSON/CSV. The helper uses six source-hash-guarded overlays to fix upstream-only compiler and linker warnings (including RX/RW ELF segments instead of RWX) and explicitly rejects a future RWX BIOS. See [cleanup evidence](../../docs/DEV_TOOLCHAIN_WARNING_CLEANUP.md). `build_probe.sh` **deliberately uses `run=False`**; it never calls ISE place-and-route/BitGen, loads an SRAM image, or writes SPI flash. Do not install these artifacts on a real device.

## What is still missing (required before claiming PanoLab Rescue v1 compliance)

1. Replace compile-time lab MAC with per-unit factory identity read/validation before LiteEth initialization.
2. Extend BIOS via minimal upstream-compatible hook for configurable autoboot window, physical button hold and persistent journal policy. The exported button CSRs are the hardware foundation, **not** the completed feature.
3. Implement Spartan-6 `ICAP_SPARTAN6` FPGA reconfiguration. Upstream `ICAPE2` is incompatible; test the IPROG sequence and boot addressing.
4. Design, size and verify a safe RESCUE/APP_A/APP_B/IDENTITY/STATE flash map against actual built bitstreams, factory header and JEDEC geometry; do **not** blindly reuse stock offsets.
5. Build bounded Ethernet management using LiteX BIOS/LiteEth routines; implement A/B transactional updates, readback/digests, profile-aware access, trial confirmation and rollback. BIOS `netboot` and `flashboot` boot CPU software, **not** FPGA slots.
6. Run a full pinned vendor ISE build, check timing/resource use, then—with exact owner approval—perform G2 read-only bring-up and power-cycle/button recovery checks before any irreversible flash conversion.

**Factory-history reference only:** the reverse-engineered G2 factory map has a multiboot header near `0x000000`, golden image around `0x040000`, main around `0x480000`, and device identity data around `0x8c0000`. These offsets are not the new PanoLab partition layout. Confirm revision, image header and erase geometry from independent board evidence before destructive action.

All implementation lives on `development`, with `main` frozen. No G2 flash operation or deployment is authorized solely by building this source.
