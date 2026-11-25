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
| [Current engineering baseline and G2 handoff](docs/ENGINEERING_BASELINE.md) | Tested source/configuration inventory, running services, publication gates and G2 handoff |
| [Temporary components and retirement register](docs/TEMPORARY_COMPONENTS.md) | Preserve accelerated maintenance, old one-time scripts and rollback assets until a tested replacement exists |
| [Architecture and baseline decisions](docs/ARCHITECTURE.md) | What exists, system boundaries, G2 design and planned capabilities |
| [Source and Project Architecture Standard](specs/PANOLAB_SOURCE_AND_PROJECT_ARCHITECTURE.md) | Authoritative planned ownership and layout for projects, BSPs, upstream source, manifests, licensing and releases |
| [Install and operate](docs/GETTING_STARTED.md) | Host prerequisites, private inputs, rootless deployment, status and recovery limits |
| [Develop, test and publish](docs/DEVELOPMENT.md) | Laptop-local testing, appropriate CI use and verified low-noise commits |
| [Security](docs/SECURITY.md) | Credentials, mounts, rootless authority, approval gates and hardware safety |
| [Toolchain MCP contract](docs/TOOLCHAIN_MCP_CONTRACT.md) | Persistent vendor build worker and canonical five MCP tools |
| [ISE 14.7 licensed implementation evidence](docs/ISE14_REMOTE_BRINGUP_EVIDENCE.md) | Two successful real six-stage Spartan-6 builds, hashes and node-locked network repair |
| [Remote iteration architecture](docs/REMOTE_ITERATION_ARCHITECTURE.md) | Live source staging, temporary trusted maintenance, recovery boundaries and retirement plan |
| [ISE remote milestone review](docs/ISE14_REMOTE_MILESTONE_REVIEW.md) | Permanent-versus-temporary file inventory, checkpointed images and acceptance gaps |
| [ISE setup on-demand stress test](docs/ISE14_SETUP_ONDEMAND_STRESS.md) | Real stop/start, media and installer guards, licensed build with setup offline, and outstanding provisioning tests |
| [Clean-host admission and remaining blockers](docs/FRESH_HOST_ACCEPTANCE.md) | Read-only missing-prerequisite report, isolated empty-host test, launcher corrections and strict unprovisioned-host acceptance gates |
| [Disposable unattended ISE installation acceptance](docs/ISE14_DISPOSABLE_INSTALL_ACCEPTANCE.md) | Normal MCP-driven fresh vendor installation, scoped terms approval, real bitstream and automatic test-only disposal |
| [Agent instructions](AGENTS.md) | Rules for automated engineering sessions |
| [LM1 first working lab milestone](specs/LAB_MILESTONE_1.md) | Software acceptance evidence, design lessons and LM2 demonstration |
| [PanoLab Rescue v1 standard](specs/PANOLAB_RESCUE_V1.md) | Cross-platform boot, A/B update, identity, BSP, trust profiles and qualification contract |
| [LiteX BIOS Rescue implementation](docs/RESCUE_IMPLEMENTATION.md) | Startup timeout/button behavior, Ethernet management, unpaired Trusted-LAN profile and validation gates |
| [G2 Rev B first Rescue SoC](projects/rescue/README.md) | Pinned LiteX BIOS/VexRiscv/LiteEth/LiteSPI implementation and build helper |
| [Rescue iteration-15 engineering checkpoint](projects/rescue/experiments/iteration-15/README.md) | Preserved 15 iterations, read-only diagnostic timing proof, simulated components and pending physical qualification |
| [Stock Pano research](research/pano-stock/README.md) | Physically measured stock discovery, flash acquisition and agentic workflow |
| [G2 Rescue test evidence](docs/RESCUE_BUILD_EVIDENCE.md) | Actual generated BIOS/Verilog, nine tests, live LiteX simulation and unproven hardware gates |
| [Rootless LiteX environment recipe](docs/RESCUE_ENVIRONMENT_RECIPE.md) | Container packages, immutable source locks, clean bootstrap evidence and safe image refresh |
| [Unified development image upgrade](docs/UNIFIED_DEV_IMAGE_UPGRADE.md) | One modern FPGA development image, explicit laptop rebuild, source reconciliation and rollback plan |
| [Unified development image acceptance](docs/UNIFIED_DEV_IMAGE_ACCEPTANCE.md) | Real laptop rebuild, six-service health, 23 tests, BIOS/HDL artifacts and live LiteX BIOS simulation |
| [Toolchain warning cleanup](docs/DEV_TOOLCHAIN_WARNING_CLEANUP.md) | No-RWX BIOS link, pinned upstream C warning fixes, owner-local Buildx, and exact rollback cleanup |
| [GitHub publishing and private push setup](docs/GITHUB_PUBLISHING.md) | Development branch sources, connected GitHub writes, one-time owner credential and scoped repository gateway |
| [Upstream Rescue adoption review](specs/PANOLAB_RESCUE_UPSTREAM_ADOPTION_REVIEW.md) | Verified upstream bootloader examples, source reuse boundaries and outstanding proof |

The selected [FPGA system specification](specs/PANOLAB_DIRECT_v1_0.txt)
is the companion concise functional requirements file. Read
[Engineering Baseline](docs/ENGINEERING_BASELINE.md) for **current status**
and [Temporary Components](docs/TEMPORARY_COMPONENTS.md) for intentionally
retained non-production infrastructure. Dated acceptance reports and
migration records preserve **historical** observations, not competing
current operational instructions.

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

**Verified on the actual laptop (2026-11-24):** The separately licensed
ISE 14.7 rootless worker accepted two distinct immutable RTL revisions and
completed genuine XST, NGDBuild, MAP, PAR, TRACE and BitGen implementations.
Both returned exit code 0 and produced different nonempty 4,220,305-byte
Spartan-6 bitstreams with SHA-256 records. The existing node-locked license
works using a Docker-**internal** network with the licensed virtual Ethernet
identity; the license and laptop network interfaces were not modified.
The authenticated remote ISE interface and temporary trusted maintenance
capability are operational. On-demand setup operation was **accepted for
the existing, already-provisioned setup container**: three complete
stop/start cycles, 20 concurrent status requests, a full media inspection,
invalid-install rejection, and a real licensed six-stage bitstream build
while setup was stopped. The setup service is now stopped with `restart: no`;
its Compose profile is optional, and manager/tunnel startup dependencies
on setup have been removed. **Seven containers are currently active**:
the proposed six steady-state services plus the *temporary* trusted-
maintenance sidecar. Full six-service reboot and fresh-host provisioning
are still unverified. Prior worker rollback containers remain stopped. See
[licensed implementation evidence](docs/ISE14_REMOTE_BRINGUP_EVIDENCE.md)
and [remote iteration decisions](docs/REMOTE_ITERATION_ARCHITECTURE.md).

**Separately accepted on the actual laptop:** The normal PanoLab
manager/broker ran **two complete disposable ISE 14.7 installations**
from fresh named install/work volumes, with no manual EULA interaction
or temporary maintenance test execution. Both archive checks,
unattended native vendor installations and genuine six-stage
Spartan-6 bitstream builds succeeded. Each generated a separate
4,220,305-byte bitstream, and **all eight resources per run were
deleted and independently checked absent**. The private license,
persistent ISE installation, stopped normal setup and running worker
were unchanged. The accepted media and owner authorization are pinned
by a SHA-256 policy file; different terms/media require new approval.
See [the real disposable installation evidence](docs/ISE14_DISPOSABLE_INSTALL_ACCEPTANCE.md).
This proves vendor installation on the provisioned rootless laptop,
**not** a complete unprovisioned-host appliance install.

**Fresh-host admission check (2026-11-24):** The normal launcher now
offers `--fresh-host-check`, a read-only prerequisite inventory that works
before Docker or private credentials are configured. Eight clean-room
admission/launcher tests passed, and the on-demand setup Compose assumptions
in the main installer were corrected. An isolated empty-home simulation
correctly **blocked** on missing prerequisites; a separate clean Linux
VM/laptop has **not yet been provisioned or tested**. See
[clean-host acceptance evidence](docs/FRESH_HOST_ACCEPTANCE.md).

**Still unverified:** a completely unprovisioned host installation,
reboot recovery of the revised on-demand system, actual Rescue G2 boot, physical Etherbone traffic,
and Rescue programming/flash. A G2 Rev B read-only diagnostic candidate did pass ISE timing; see the [iteration-15 checkpoint](projects/rescue/experiments/iteration-15/README.md). Separate stock-device Ethernet discovery and full SPI address-space acquisition passed; no FPGA programming was performed.
The historical [LM1 milestone](specs/LAB_MILESTONE_1.md) remains the accepted
six-service baseline, not evidence of the new eight-container reboot test.

## Unified development container

**The modern Docker image is a single, shared FPGA development toolchain** with Python, HDL simulation, RISC-V GCC, LiteX BIOS, LiteEth, LiteSPI, Migen, VexRiscv and Codex. Its [Dockerfile](docker/modern/Dockerfile) separates tools by function within one recipe. Board-specific FPGA configuration is a BSP; only licensed legacy ISE 14.7 remains a separately specialized build environment. [Controlled dev-only upgrade](docs/UNIFIED_DEV_IMAGE_UPGRADE.md) explains how to move the existing dev container onto the rebuilt image without replacing the five management services.

## Temporary remote maintenance during engineering

The owner-approved `trusted-maintenance` profile permits remote management
of the **ordinary-user rootless Docker Engine**, including container rebuild
and recovery. Broker Python modules are read from a live read-only directory
mount; new FPGA input revisions are staged atomically into private,
content-addressed worker projects. This is a **temporary broad-authority
development exception**, not a production-grade policy. No vendor license,
tokens, bitstreams or host identifiers belong in Git. Consult
[the reviewed temporary controls and rollback plan](docs/ISE14_REMOTE_MILESTONE_REVIEW.md)
before changing the profile.

The temporary bridge remains **intentionally operational**
for rapid owner-approved inspection and correction during G2 development.
It is **not** the executor of normal `@ise14`, `@setup` or
`@ise-e2e` acceptance flows. Its removal is gated on a tested
restricted updater and independent rollback. Historical one-time
scripts such as `host/ise14-repair.py`,
`host/activate-ise-bridge.sh`, `host/apply-source-migration.sh`
and `host/reconcile-and-upgrade.sh` are preserved, clearly classified
in [the host script index](host/README.md), and **must not be rerun**
against the current commit.

## Entrypoint

Run as the ordinary laptop user, with rootless Docker and private inputs
already provisioned (see [setup](docs/GETTING_STARTED.md)):

```sh
bash ./panolab-install.sh --fresh-host-check  # read-only prerequisite inventory
bash ./panolab-install.sh --status
bash ./panolab-install.sh --check
bash ./panolab-install.sh --upgrade-dev   # explicit, guarded dev-only image upgrade
bash ./panolab-install.sh --enable-github-push  # optional one-time private gateway write credentials
bash ./panolab-install.sh
```

No `sudo`, host-wide Docker cleanup, FPGA programming or GitHub CI
is part of the installer. Source and third-party vendor media must not
be confused: credentials, license files, ISE installers and build
outputs stay in private ignored locations.

## Source organization

PanoLab's [Source and Project Architecture Standard](specs/PANOLAB_SOURCE_AND_PROJECT_ARCHITECTURE.md) governs source ownership. The source organization is migrated in this development candidate; **a live laptop service cutover is a separate acceptance gate**. The unified modern development image still contains historical bootstrap checkouts, but project builds intentionally resolve the verified committed snapshots in `third_party/`, not the image copies.

| Directory | Active role |
| --- | --- |
| `projects/rescue/` | Complete Rescue project: `project.toml`, SoC, BIOS integration, build and tests |
| `boards/pano_g2_rev_b/` | Reusable physical G2 Rev B BSP and board-specific constraints |
| `research/` | Owner-approved independent research, including stock Pano protocol and flash evidence (no private images) |
| `shared/` | Common PanoLab project source resolver and future reusable RTL/components |
| `third_party/` | Selected, versioned LiteX, Migen, LiteEth, LiteSPI, Picolibc and VexRiscv source snapshots with licenses and checksums |
| `docker/` | Container images, modern toolchain, broker, Git gateway, manager and isolated vendor ISE sources |
| `host/` | Rootless installation, lifecycle and guarded dev-image upgrade |
| `tests/` | Cross-project regression tests and simulation fixtures |
| `agent/` | Agent integration policy and capabilities |
| `specs/` | Engineering and product standards |
| `docs/` | Operations, architecture and verified evidence |

**G2 Rescue source build** (inside the verified modern development environment with a checked-out source tree):

```bash
export PANOLAB_LAB_MAC=02:00:00:00:00:01  # single isolated lab only
bash projects/rescue/test.sh
bash projects/rescue/build.sh
```

Source-verifier enforcement selects the committed snapshots from the central registry. Outputs are generated outside the repository, by default under `/workspace/panolab-projects/rescue-g2b/`. The actual LiteX BIOS C source is versioned in `third_party/litex/afed6623/src/litex/soc/software/bios/`. The output `bios.bin` is not a committed source file and is not a hardware-ready image. See [Rescue artifacts](projects/rescue/ARTIFACTS.md) and [candidate migration acceptance](docs/SOURCE_MIGRATION_ACCEPTANCE.md).

**Publish only working milestones:** experiment and verify inside the
laptop's local containers, review changes, then make one coherent
commit. GitHub CI is optional for small, justified clean-runner checks,
not a replacement for testing the actual laptop.
