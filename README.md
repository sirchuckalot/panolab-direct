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

**Not yet verified:** a completely unprovisioned host installation,
licensed ISE implementation, pinned LiteX dependencies, G2 Rev B
constraints/bitstream or physical FPGA/Etherbone operation.
See the [milestone record](specs/LAB_MILESTONE_1.md) for exact evidence
and limitations.

## Entrypoint

Run as the ordinary laptop user, with rootless Docker and private inputs
already provisioned (see [setup](docs/GETTING_STARTED.md)):

```sh
bash ./panolab-install.sh --status
bash ./panolab-install.sh --check
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
| `boards/`, `agent/` | Minimal placeholders for upcoming G2 integration |
| `gateware/` | G2 implementation placeholder and a simulation-only CSR demonstration |
| `docs/` | The five current engineering documents linked above |

**Publish only working milestones:** experiment and verify inside the
laptop's local containers, review changes, then make one coherent
commit. GitHub CI is optional for small, justified clean-runner checks,
not a replacement for testing the actual laptop.
