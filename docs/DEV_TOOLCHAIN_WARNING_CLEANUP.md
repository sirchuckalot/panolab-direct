# Development Toolchain Warning Cleanup — Scoped Maintenance

Historical record of the exact owner-approved maintenance operation. See [operations](GETTING_STARTED.md) for current entry points.

**Record:** PLR-ENV-004 | **Date:** November 23, 2026 Pacific / November 24 UTC | **Status:** **LAPTOP_MAINTENANCE_ACCEPTED**: warning-free G2 BIOS source build; owner-side Buildx installation and exact rollback-container deletion completed, with six live services independently verified. A fresh image rebuild using Buildx remains separately untested.

## System boundary

PanoLab retains **one** modern developer image `panolab-direct-modern:local` and the separately isolated licensed ISE toolchain. No new dev image is created for Buildx or LiteX. Docker Buildx is a *host CLI plugin* controlling the existing owner's rootless Docker engine, not another daemon or image. Docker's legacy builder is part of the Docker CLI fallback; there is **no separate legacy builder container to delete**. Eliminating reliance on it means installing a functional Buildx CLI and using `docker buildx build --builder default --load` explicitly for image builds.

The owner-only, pinned [Buildx installer](../host/install-rootless-buildx.sh) obtains Docker Buildx **v0.36.1** from the official GitHub release using its published SHA-256 `48af8a397ebd60178778bf63611dbcebe5f5e7a9be90eb9147b24b9587455778`. Installs under `~/.docker/cli-plugins` without `sudo` or host `apt` and preserves any working existing Buildx plugin. This is necessary on the **host**, not inside the development container, because image construction is managed by the host Docker CLI. It requires network access for the verified binary if Buildx isn't installed.

The existing [rootless installer](../host/rootless-install.sh) and [dev-only upgrade helper](../host/upgrade-dev-image.sh) now use Buildx/BuildKit for new image builds; the default `docker` driver uses the same rootless Engine, not an auxiliary `docker-container` BuildKit worker.

## BIOS warnings — root cause and verified fixes

The last fully successful unified-image installation built the G2 Rescue BIOS with warnings about Compiler-RT function declarations, unused LiteSPI helpers, the no-SFP stub prototype and a genuinely RWX ELF program segment. These warnings were in **pinned upstream sources**, not evidence that a newer version was required. Rather than mutating upstream checkouts or disabling warning flags, PanoLab now uses [six pinned-context source overlays](../projects/rescue/soc/bios_source_overlay.py), staged under the build output's `source_overlays` directory. Each overlay verifies the exact SHA-256 of its upstream input, then changes only a local working copy.

| Origin | Actual cause | Targeted correction |
| --- | --- | --- |
| `compiler-rt/comparesf2.c` and `comparedf2.c` | Vintage LLVM `FNALIAS` macro declares old-style no-parameter `void name()` | Declare correctly typed float/double ABI aliases with their original functions; keep addresses/semantics |
| `liblitespi/spiflash.c` | Write helper is only used for Quad/QPI configuration but compiled even for the single-lane M25P128 model | Compile that helper only when Quad/QPI capability is defined |
| `libliteeth/sfp.c` | No-SFP configuration compiles a stub without having seen its public header | Include the existing upstream `libliteeth/sfp.h` declaration unconditionally |
| `bios/Makefile` | Upstream linker line uses `-N`, which requests writable text | Drop `-N` in the build-only overlay |
| `bios/linker.ld` | Default ELF program headers map executable code into an RWE segment | Add explicit ROM `PT_LOAD FLAGS(5)` (R-X) and SRAM `PT_LOAD FLAGS(6)` (RW-); mark NOLOAD boot scratch `:NONE` |

**Live validation:** The new BIOS compiled from freshly staged pinned source overlays with **zero lines containing `warning:` or `error:`**. `riscv64-unknown-elf-readelf -lW bios.elf` showed two distinct `LOAD` segments with `R E` and `RW`, and **no `RWE` load segment**. The resulting BIOS remained **39,156 bytes**, and generated G2 Verilog **492,579 bytes**. Icarus HDL syntax and all **nine G2 source/button tests** passed. The SHA-256-guarded new overlay and host maintenance tests passed **13/13**, including two fake-Docker safety fixtures (only the exact stopped rollback removed; a foreign container refused). The new clean G2 test artifacts are under `/workspace/panolab-warning-fixes/out/validated`; source warnings log under `/workspace/panolab-warning-fixes/build-validated.log`.

The ROM-region binary layout matches the previous image through the vast majority of bytes, with small final-byte differences due to compiler/link metadata; the new ELF's final segment permissions and region layout were inspected. This is **not yet** a physically exercised FPGA image; the current G2 target does not produce a Spartan-6 `.bit`. The firmware build now fails if any RWX LOAD segment reappears.

## Cleanup procedure

After the new checkout and modern tools have been confirmed, run the *explicit* owner-only maintenance entry point:

```sh
bash ./panolab-install.sh --finalize-maintenance
```

It checks the user-level rootless Engine, accepted image recipe and identity of the running dev, unchanged persistent workspace mount, actual tool availability, a working Buildx plugin, and the **existing default docker driver**.

It then removes only the known stopped container object:

```text
panolab-direct-dev-1-rollback-20261124T020818Z
```

No stop/restart of the running modern container, no pruning of images, builder caches, Docker volumes or file-system paths, and no alteration of the ISE environment. The historical Git backup branch remains preserved. If a container doesn't match the expected name, state, image or mounted workspace, the cleanup fails closed. If the rollback is already absent, the maintenance operation is idempotent.

The old rollback's `Exited (137)` status is historical evidence; deleting the stopped container does **not** explain the exit code. The previous migration explicitly stopped that container; a code 137 can represent SIGKILL and is not proof of memory exhaustion. We do not attribute a precise cause without host evidence.

## Owner execution and independent confirmation

On November 23, 2026 (Pacific), the owner ran `bash ./panolab-install.sh --finalize-maintenance` from the existing laptop checkout. The returned terminal output showed:

- `PanoLab rootless: PASS`: existing rootless engine, owner credentials/data and merged Compose passed preflight.
- `BUILDX_PLUGIN=PASS github.com/docker/buildx v0.36.1 1d8dde89b8aba914e05e45366770736fea1fd690`: the checksum-pinned owner-local CLI plugin was successfully installed and recognized.
- `BUILDKIT_DEFAULT_DRIVER=PASS`: the existing rootless engine uses the default Docker driver, without an additional BuildKit daemon/container.
- `ROLLBACK_CONTAINER_REMOVED=PASS`: only `panolab-direct-dev-1-rollback-20261124T020818Z` was deleted.
- `SIX_SERVICE_HEALTH=PASS`: all expected services passed the maintenance helper's health checks; no global prune or FPGA operation.

A subsequent **independent PanoLab MCP `lab_status`** listed exactly six running services (`dev`, `tunnel`, `manager`, `repo-git`, `docker-broker`, `setup`) and no rollback container. `repo_status` confirmed a clean `development` checkout at `f03660d759bd532834c4b1948e054dde69b963ea` before this documentation-only acceptance update.

This is evidence for plugin installation and safe old-container cleanup. It is **not** evidence of a fresh image build using Buildx; the already running unified development image does not need to be rebuilt for a host CLI-plugin change. The historical old-container exit code `137` remains unexplained and does not affect this accepted cleanup.

## Acceptance gates

- **PASS:** patched G2 BIOS source build, warning count zero, ELF RX/RW load segments, source and RTL regression tests.
- **PASS:** staged host scripts pass `bash -n`; offline contracts for Buildx checksum, legacy builder replacement, exact rollback cleanup and absence of broad prune pass.
- **PASS — OWNER LAPTOP:** Buildx v0.36.1 installed and accepted; default BuildKit driver validated; exact stopped rollback container removed; six remaining services independently confirmed running.
- **PENDING:** actual host Buildx rootless image rebuild (when next required), generic LiteX live simulation of the **patched G2 BIOS** rather than the already accepted generic upstream simulation, vendor ISE/G2 hardware qualification and real PHY/SPI identification.

**Do not interpret a clean compiler log as proof of bootable physical FPGA hardware, valid SPI writes or production recovery security.**
