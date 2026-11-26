# PanoLab Direct — agent engineering contract

This file is executable-session guidance for the **current
baseline**, not an experiment log. Start at the repository
[README](README.md), the [engineering handoff](docs/ENGINEERING_BASELINE.md)
and the [temporary-component register](docs/TEMPORARY_COMPONENTS.md);
then read [architecture](docs/ARCHITECTURE.md),
[installation/operations](docs/GETTING_STARTED.md),
[development](docs/DEVELOPMENT.md), [security](docs/SECURITY.md),
and the [five-tool ISE contract](docs/TOOLCHAIN_MCP_CONTRACT.md).
Read [PanoLab Rescue v1](specs/PANOLAB_RESCUE_V1.md) for the
approved forward boot/update/recovery standard (not yet fully implemented or physically qualified).
Read the [iteration-15 Rescue checkpoint](projects/rescue/experiments/iteration-15/README.md) and [stock research](research/pano-stock/README.md) before resuming G2 hardware work. Keep original experimental evidence separate from the canonical project build.
Read the [LiteX BIOS implementation plan](docs/RESCUE_IMPLEMENTATION.md)
for the timed/button-held recovery workflow and the deliberately unpaired
Trusted-LAN appliance profile. That device mode does **not** waive
owner approval for physical writes through the laptop MCP agent.

**Source/project architecture authority:** Read the
[PanoLab Source and Project Architecture Standard](specs/PANOLAB_SOURCE_AND_PROJECT_ARCHITECTURE.md)
before adding, moving, or changing a project, board BSP, reusable RTL,
upstream source snapshot, product dependency, source license or release
workflow. it is the authoritative organization and provenance standard. The
source migration has established `projects/`, `shared/` and
`third_party/` in the development source candidate; **do not assume
the running laptop containers have been cut over** until the recorded
runtime acceptance gates pass.

**Mandatory hard-stop policy:** Both ChatGPT and Codex SHALL follow [Agent execution and hard-stop policy](docs/AGENT_EXECUTION_POLICY.md) before every session and dependent gate. Missing required resources or execution-framework failures are immediate `INFRASTRUCTURE_BLOCKED` outcomes: stop, report first, correct the cause and verify the original path before resuming. No silent skips or workarounds.

**Delegated engineering and frozen Rescue boundary:** ChatGPT owns in-scope system design, scope control and independent acceptance; Codex owns implementation, engineering tests and technical implementation documentation. Do not wait for routine owner decisions already supported by the specifications. `projects/rescue/` is immutable engineering history; Anchor must contain its own selected product source and tests and must build/test/stage without Rescue. Use only declared BSP/shared/upstream/platform dependencies. See the binding [agent execution policy](docs/AGENT_EXECUTION_POLICY.md) and [source architecture §6.1](specs/PANOLAB_SOURCE_AND_PROJECT_ARCHITECTURE.md#61-anchor-product-independence-and-frozen-rescue-history).

## What is real, and what is planned

- The owner's laptop currently runs **seven** rootless PanoLab
  containers: authenticated tunnel, manager, broker, Git gateway,
  modern HDL/Codex development, persistent licensed ISE worker, and
  **temporary trusted maintenance**. The optional ISE setup container
  is **stopped** with `restart: no`. The proposed steady state has
  six services after independently qualifying and retiring the
  temporary maintenance bridge. Local authenticated MCP, licensed
  builds and resource-limit evidence exist.
- GitHub `main` at `006b6ee` is the accepted software lab baseline.
  The owner's canonical checkout at `~/Projects/repos/panolab-direct-main`
  is now on `development`, tracking GitHub `development`; source tests,
  clean project reinstall, authenticated MCP and post-reboot service
  recovery passed on that **already provisioned** laptop.
- The unified modern image recipe pins LiteX, LiteEth, LiteSPI, Migen,
  VexRiscv, RISC-V C tools and BIOS. The unified rootless Docker image
  **was rebuilt and laptop-verified** with 23 tests and a live generic LiteX
  BIOS session ([PLR-ENV-003](docs/UNIFIED_DEV_IMAGE_ACCEPTANCE.md)).
  Licensed ISE 14.7 has now completed multiple genuine six-stage
  Spartan-6 implementations, including **two unattended disposable
  vendor installations entirely through the normal MCP path**.
  Physical FPGA acceptance, **completely unprovisioned-host installation**
  and the revised six-service reboot test remain **PENDING**. The
  historical six-service laptop reboot test passed only after setting
  the standalone dev container restart policy; source tests or CI
  alone cannot prove the expanded operating state.
- Target Pano Logic **G2 Rev B**, XC6SLX150-2-FGG484. Planned
  CPU-less LiteX/LiteEth/Etherbone, bounded CSR access, then LiteScope
  and coherent framebuffer observation. USB3300 is not baseline RTL.
- Persistent vendor build worker and MCP server reside in **one
  runtime container**. Exactly five agent-facing build tools:
  `toolchain_info`, `build_start`, `build_status`,
  `build_result`, `build_cancel`. No added vendor-specific tools
  without explicit owner approval.

## Toolchain warning and legacy-builder policy

Never silently silence BIOS compiler/linker warnings. The pinned-context
[Rescue BIOS build overlay](projects/rescue/soc/bios_source_overlay.py)
creates modified **build-output copies**, leaving pinned Git and
installed Pythondata files intact. The G2 build must fail on an RWE/RWX
ELF load segment. When upstream changes, update six exact SHA-256 guards
and rerun the BIOS, HDL and source regression tests before publishing.
Docker CLI Buildx belongs in the owner-local CLI plugin directory,
not the general development image and not another BuildKit container.
The [exact owner-approved rollback cleanup](docs/DEV_TOOLCHAIN_WARNING_CLEANUP.md)
is a separate, guarded host operation; never globally prune.

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

## GitHub source publishing boundary

GitHub `main` is the default branch and is **not** the active Rescue
source. The [`development` branch](https://github.com/sirchuckalot/panolab-direct/tree/development)
contains the implementation. Rescue now selects source-verified
`third_party/` snapshots via its `project.toml`; historical upstream
checkouts inside the current modern image are toolchain bootstrap inputs,
**not** the authority for a Rescue product build.
The connected GitHub app is already authorized for server-side commits.
The laptop `repo-git` gateway previously failed direct `repo_push`
due to missing HTTPS authentication; the optional
[one-time owner-private push setup](docs/GITHUB_PUBLISHING.md)
allows **only** non-force `development` pushes. Never request token
material in chat, mount it in `dev`, or publish it in logs.

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

## Fresh-host admission versus acceptance

The read-only `panolab-install.sh --fresh-host-check` inventories
prerequisites before Docker or private credentials exist. It reports
missing facilities and **does not install packages or provision secrets**.
The [fresh-host admission report](docs/FRESH_HOST_ACCEPTANCE.md)
documents an isolated empty-checkout/home check and installer corrections.
This is **not** an accepted clean laptop deployment: the normal
environment cannot create an independent KVM/QEMU host, and first-time
OS/runtime/private-credential provisioning is still unresolved.
Do not claim a fresh-host PASS from the read-only fixture or the
separately successful disposable ISE vendor-install runs.

## Security and change boundaries

- Rootless container UID 0 maps to the ordinary owner's UID, not
  host root. Restricted broker access to the user Docker socket
  still carries broad authority over the owner's Docker resources.
- No host `sudo`, package installation, system/rootful Docker
  changes, broad `$HOME` mounts, privileged containers or global
  Docker cleanup. Never bypass MCP broker allowlists.
- Preserve the running manager, tunnel, Codex authentication, private
  ISE media/license, project workspace and other applications.
  The [external-storage candidate](docs/EXTERNAL_STORAGE_CUTOVER.md) keeps
  secrets in `PANOLAB_CONFIG_DIR` and operational data in `PANOLAB_DATA_DIR`,
  outside the checkout. The live baseline uses `docker/private/` and ignored
  `docker/.env` until cutover. Keep all of these private. The candidate dev
  mount exposes the canonical checkout read-only at `/repo` with a read-only
  `/repo/.git` mask, and has dedicated writable workspace and Codex auth binds.
- No physical FPGA programming, JTAG, SPI flash modification, volatile
  configuration or unbounded Etherbone access without specific
  owner authorization and a credible recovery path.
- A software source PASS, licensed toolchain PASS and physical board
  PASS are **different evidence levels**. State commands,
  execution location and limitations accurately.

## Documentation and publication hygiene

Maintain the **current operational baseline** in
[architecture](docs/ARCHITECTURE.md) and the **authoritative future source/project
structure, third-party, provenance and licensing decisions** in the
[source and project standard](specs/PANOLAB_SOURCE_AND_PROJECT_ARCHITECTURE.md).
Do not duplicate or silently override either authority. The verified first software
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
