# PanoLab Direct

**Rootless Docker FPGA development laboratory on the owner's Linux laptop.**

PanoLab Direct provides a containerized HDL/Codex development environment,
restricted source and Docker management, an authenticated MCP connection from
ChatGPT, and a provisioned path for a separately licensed Xilinx ISE 14.7
build worker. The FPGA target is **Pano Logic G2 Rev B
(XC6SLX150-2-FGG484)** with a future CPU-less LiteX/LiteEth/Etherbone design.

## Start here

| Read | What it covers |
| --- | --- |
| [Architecture and baseline decisions](docs/ARCHITECTURE.md) | What exists, system boundaries, G2 design and planned capabilities |
| [Install and operate](docs/GETTING_STARTED.md) | Host prerequisites, private inputs, rootless deployment, status and recovery limits |
| [Develop, test and publish](docs/DEVELOPMENT.md) | Laptop-local testing, appropriate CI use and verified low-noise commits |
| [Security](docs/SECURITY.md) | Credentials, mounts, rootless authority, approval gates and hardware safety |
| [Toolchain MCP contract](docs/TOOLCHAIN_MCP_CONTRACT.md) | Persistent vendor build worker and canonical five MCP tools |
| [Agent instructions](AGENTS.md) | Rules for automated engineering sessions |
| [LM1 first working lab milestone](specs/LAB_MILESTONE_1.md) | Software acceptance evidence, design lessons and LM2 demonstration |
| [PanoLab Rescue v1 standard](specs/PANOLAB_RESCUE_V1.md) | Cross-platform boot, A/B update, identity, BSP, trust profiles and qualification contract |
| [LiteX BIOS Rescue implementation](docs/RESCUE_IMPLEMENTATION.md) | Startup timeout/button behavior, Ethernet management, unpaired Trusted-LAN profile and validation gates |
| [G2 Rev B first Rescue SoC](boards/pano_g2_rev_b/README.md) | Pinned LiteX BIOS/VexRiscv/LiteEth/LiteSPI implementation and build helper |
| [G2 Rescue test evidence](docs/RESCUE_BUILD_EVIDENCE.md) | Actual generated BIOS/Verilog, nine tests, live LiteX simulation and unproven hardware gates |
| [Rootless LiteX environment recipe](docs/RESCUE_ENVIRONMENT_RECIPE.md) | Container packages, immutable source locks, clean bootstrap evidence and safe image refresh |
| [Unified development image upgrade](docs/UNIFIED_DEV_IMAGE_UPGRADE.md) | One modern FPGA development image, explicit laptop rebuild, source reconciliation and rollback plan |
| [Unified development image acceptance](docs/UNIFIED_DEV_IMAGE_ACCEPTANCE.md) | Real laptop rebuild, six-service health, 23 tests, BIOS/HDL artifacts and live LiteX BIOS simulation |
| [Toolchain warning cleanup](docs/DEV_TOOLCHAIN_WARNING_CLEANUP.md) | No-RWX BIOS link, pinned upstream C warning fixes, owner-local Buildx, and exact rollback cleanup |
| [Upstream Rescue adoption review](specs/PANOLAB_RESCUE_UPSTREAM_ADOPTION_REVIEW.md) | Verified upstream bootloader examples, source reuse boundaries and outstanding proof |

The selected [FPGA system specification](specs/PANOLAB_DIRECT_v1_0.txt)
is the companion concise functional requirements file. These documents
describe the **current baseline and forward design**, not an experiment
log or chronology of past engineering attempts.

## Operational baseline

**LM1 accepted on the owner's already provisioned laptop (2026-11-23):**
a project-only tear-down, unmodified-installer rebuild and authenticated
MCP acceptance succeeded. The six rootless Docker services recovered
automatically after a reboot once the standalone development container
was configured with `unless-stopped`. Kernel-enforced 2-CPU, 4-GiB,
256-PID limits, Codex authentication and HDL smoke simulation passed.

GitHub has only `main` (accepted software baseline `006b6ee`) and
`development` (active engineering); both were identical at the LM1
freeze. The canonical checkout `~/Projects/repos/panolab-direct-main`
has **`development` checked out**, irrespective of its folder name.
All new work happens on `development`; `main` changes only after
owner-approved promotion.

**Verified on the actual laptop (2026-11-23 Pacific):** the unified modern Docker image rebuilt and passed rootless deployment acceptance: **23 tests**, all seven pinned LiteX sources, CPU/memory/PID limits, generated G2 BIOS/Verilog/UCF, and a live generic LiteX BIOS console. See [full acceptance evidence](docs/UNIFIED_DEV_IMAGE_ACCEPTANCE.md).

**Verified in the laptop development container:** a follow-up clean G2 BIOS source build using pinned-context overlays now emits no compile/link warnings and has separate RX/RW ELF load segments. The owner-local Buildx v0.36.1 installation and precise rollback-container cleanup have **now passed** on the laptop, with six live services independently verified. A fresh Buildx image rebuild has not yet been needed or tested. See [cleanup evidence](docs/DEV_TOOLCHAIN_WARNING_CLEANUP.md).

**Not yet verified:** completely unprovisioned host installation, licensed ISE implementation, Spartan-6 bitstream, real Pano G2 boot or physical FPGA/Etherbone operation.
See the [milestone record](specs/LAB_MILESTONE_1.md) for exact evidence
and limitations.

## Unified development container

**The modern Docker image is a single, shared FPGA development toolchain** with Python, HDL simulation, RISC-V GCC, LiteX BIOS, LiteEth, LiteSPI, Migen, VexRiscv and Codex. Its [Dockerfile](docker/modern/Dockerfile) separates tools by function within one recipe. Board-specific FPGA configuration is a BSP; only licensed legacy ISE 14.7 remains a separately specialized build environment. [Controlled dev-only upgrade](docs/UNIFIED_DEV_IMAGE_UPGRADE.md) explains how to move the existing dev container onto the rebuilt image without replacing the five management services.

## Entrypoint

Run as the ordinary laptop user, with rootless Docker and private inputs
already provisioned (see [setup](docs/GETTING_STARTED.md)):

```sh
bash ./panolab-install.sh --status
bash ./panolab-install.sh --check
bash ./panolab-install.sh --upgrade-dev   # explicit, guarded dev-only image upgrade
bash ./panolab-install.sh
```

No `sudo`, host-wide Docker cleanup, FPGA programming or GitHub CI
is part of the installer. Source and third-party vendor media must not
be confused: credentials, license files, ISE installers and build
outputs stay in private ignored locations.

## Source organization

| Directory | Active role |
| --- | --- |
| `host/` | Rootless user-level installer and Compose overlay |
| `docker/` | Compose recipes, modern toolchain, broker, Git gateway, manager and ISE sources |
| `tests/` | Laptop-local source/protocol tests and external ISE fixture |
| `specs/` | G2 functional design baseline |
| `boards/` | Active G2 Rev B LiteX Rescue source, source lock and rootless build helper |
| `agent/` | Agent integration design and ongoing capabilities |
| `gateware/` | G2 implementation placeholder and a simulation-only CSR demonstration |
| `docs/` | Architecture, operation, toolchain, Rescue implementation and verification records |

**Publish only working milestones:** experiment and verify inside the
laptop's local containers, review changes, then make one coherent
commit. GitHub CI is optional for small, justified clean-runner checks,
not a replacement for testing the actual laptop.
