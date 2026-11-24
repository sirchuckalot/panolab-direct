# PanoLab Direct — agent engineering contract

This file is the executable-session guidance for the **current
baseline**, not an experiment log. Start at the repository
[README](README.md), then read [architecture](docs/ARCHITECTURE.md),
[installation/operations](docs/GETTING_STARTED.md),
[development](docs/DEVELOPMENT.md), [security](docs/SECURITY.md),
and the [five-tool ISE contract](docs/TOOLCHAIN_MCP_CONTRACT.md).
Read [PanoLab Rescue v1](specs/PANOLAB_RESCUE_V1.md) for the
approved forward boot/update/recovery standard (not yet implemented).
Read the [LiteX BIOS implementation plan](docs/RESCUE_IMPLEMENTATION.md)
for the timed/button-held recovery workflow and the deliberately unpaired
Trusted-LAN appliance profile. That device mode does **not** waive
owner approval for physical writes through the laptop MCP agent.

## What is real, and what is planned

- The owner's laptop operates six rootless Docker PanoLab services:
  authenticated tunnel, manager, broker, Git gateway, ISE setup and
  modern HDL/Codex development. Local remote MCP and resource-limit
  evidence exist.
- GitHub `main` at `006b6ee` is the accepted software lab baseline.
  The owner's canonical checkout at `~/Projects/repos/panolab-direct-main`
  is now on `development`, tracking GitHub `development`; source tests,
  clean project reinstall, authenticated MCP and post-reboot service
  recovery passed on that **already provisioned** laptop.
- The unified modern image recipe pins LiteX, LiteEth, LiteSPI, Migen,
  VexRiscv, RISC-V C tools and BIOS; source-level G2 BIOS compilation and
  simulation passed. The **new complete rootless Docker image rebuild**,
  licensed ISE implementation, physical FPGA operation and fresh host
  provisioning remain **PENDING**. A
  laptop reboot test passed only after setting the standalone dev
  container restart policy; source tests or CI alone cannot prove it.
- Target Pano Logic **G2 Rev B**, XC6SLX150-2-FGG484. Planned
  CPU-less LiteX/LiteEth/Etherbone, bounded CSR access, then LiteScope
  and coherent framebuffer observation. USB3300 is not baseline RTL.
- Persistent vendor build worker and MCP server reside in **one
  runtime container**. Exactly five agent-facing build tools:
  `toolchain_info`, `build_start`, `build_status`,
  `build_result`, `build_cancel`. No added vendor-specific tools
  without explicit owner approval.

## Unified container policy

Maintain **one** modern FPGA development Dockerfile at
[`docker/modern/Dockerfile`](docker/modern/Dockerfile) for compatible
open-source tools (RTL, firmware, LiteX, agents). Group the dependency
recipe into coherent, version-pinned functional sections; use BSPs for
board adaptation. Do **not** create per-tool development images or
long-lived services when another modern tool is needed. Licensed legacy
ISE 14.7 is a justified **separate vendor worker**.

When upgrading the modern image, use the explicit, rollback-capable
[development-container procedure](docs/UNIFIED_DEV_IMAGE_UPGRADE.md).
Preserve the workspace, private Codex mount and all management services;
never silently replace an active container. Local development SHA
`f1ca3a66` and GitHub development have historically different ancestry:
follow the content-verified local backup/ref reconciliation before
changing the laptop checkout.

## Mandatory development process

1. Inspect `lab_status`, `repo_status` and live GitHub branch SHA
   before editing. Work only on `development`; `main` is frozen until
   explicit owner approval for a reviewed promotion.
2. Define the specific outcome and relevant test gate before editing.
   Work in `/workspace`, a disposable local checkout, or an
   appropriately restricted local rootless container—not in the live
   Git gateway's checkout merely for experiments.
3. **Test on the laptop** using permitted MCP tools. HDL, source,
   simulation, container, authenticated MCP and vendor integration
   acceptance belong in its containerized environment. CI can serve
   narrowly scoped, fast, deterministic clean-runner checks, but
   cannot substitute for the actual laptop, private credentials,
   licensed ISE or hardware.
4. Iterate locally **without publishing trial-and-error**. Review
   the final diff, run the appropriate local tests, record actual
   PASS and unverified PENDING gates. Only then publish **one
   coherent reviewed commit** for a working engineering milestone.
   Draft work with incomplete required gates needs explicit approval.
5. Publish reviewed source using the connected GitHub integration
   with an expected-parent non-force update. Only call `repo_sync`
   when the laptop checkout is clean and has shared ancestry with the
   target branch. Never reset, stash, force-push or discard live work
   to hide divergence.
6. Never launch extensive hosted CI/KVM or repeated GitHub commits to
   debug rootless namespaces, cgroups, Docker connectivity, private
   MCP, ISE installation or hardware. If CI is justified, state
   its narrow test purpose, budget and what success establishes.

## Security and change boundaries

- Rootless container UID 0 maps to the ordinary owner's UID, not
  host root. Restricted broker access to the user Docker socket
  still carries broad authority over the owner's Docker resources.
- No host `sudo`, package installation, system/rootful Docker
  changes, broad `$HOME` mounts, privileged containers or global
  Docker cleanup. Never bypass MCP broker allowlists.
- Preserve the running manager, tunnel, Codex authentication, private
  ISE media/license, project workspace and other applications.
  Private files in `docker/private/` and ignored `docker/.env`
  must never be published.
- No physical FPGA programming, JTAG, SPI flash modification, volatile
  configuration or unbounded Etherbone access without specific
  owner authorization and a credible recovery path.
- A software source PASS, licensed toolchain PASS and physical board
  PASS are **different evidence levels**. State commands,
  execution location and limitations accurately.

## Documentation and publication hygiene

Maintain **one current decision baseline** in
[architecture](docs/ARCHITECTURE.md). The verified first software
laboratory milestone and its evidence are recorded in
[LM1 acceptance](specs/LAB_MILESTONE_1.md). Keep implementation instructions
in [getting started](docs/GETTING_STARTED.md), test and Git workflow
in [development](docs/DEVELOPMENT.md), safety in
[security](docs/SECURITY.md) and the stable vendor API in
[toolchain contract](docs/TOOLCHAIN_MCP_CONTRACT.md).
Update the root README navigation when paths change. Do not
reintroduce duplicate decisions, debugging logs, dead links or
per-iteration commits. Preserve future design
requirements without claiming they are implemented.
