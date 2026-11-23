# PanoLab Direct — agent working contract

Read this file before changing source. The user's laptop rootless
Docker lab is the **primary execution environment**.

## Scope and architecture

- Pano Logic G2 **Rev B**, Spartan-6 XC6SLX150-2-FGG484.
- CPU-less LiteX, LiteEth/Etherbone, Wishbone/CSR; later LiteScope and
  internal framebuffer observation. No USB3300/ULPI implementation.
- Modern development and tooling run inside the laptop's rootless
  Docker containers. Legacy ISE 14.7 is a separately licensed worker
  with embedded MCP.
- The ISE worker implements exactly `toolchain_info`,
  `build_start`, `build_status`, `build_result`, `build_cancel`.
  Reuse persistent workers and keep external test fixtures external.
  Read `docs/TOOLCHAIN_MCP_CONTRACT.md` before modifying this interface.

## Mandatory workflow

1. Inspect live `lab_status`, `repo_status`, GitHub refs and worktree.
   Never infer the current state from a chat summary.
2. Read `README.md`, `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md`,
   `docs/SECURITY.md`, and relevant source before editing.
3. Select the smallest **local container test** that proves the
   next question. Use `dev_exec` for approved commands inside the
   running laptop development container, or an isolated local rootless
   container through the approved restricted broker.
4. GitHub is **for source control**. Do not run hosted KVM, Docker,
   rootless-installation, systemd, cgroup, licensed-build, tunnel or
   physical hardware acceptance tests on GitHub CI. Narrow CI-only
   repository checks require a specific justification.
5. Review changes and local test evidence. Publish reviewed source
   via the connected GitHub integration; fast-forward the clean laptop
   checkout through `repo_sync`, and check the same HEAD SHA.
   Never use a destructive local reset to resolve divergence silently.
6. State PASS/PENDING precisely, including the actual execution
   machine/container, command, output and limitations.

## Safety

- The user-scoped rootless Engine is not host root, but its broker
  can control files/resources reachable by the laptop owner.
  Do not mount its Docker socket into arbitrary agent containers.
- No sudo, host package installations, rootful daemon manipulation,
  broad home-directory mounts, privileged containers or global prune.
- Preserve running tunnel, manager, workspace, Codex auth and persistent
  workers unless a scoped, owner-approved change requires a restart.
- Private token, API key, ISE media/license and host data stay in
  `docker/private/` and ignored files, **never GitHub**.
- Do not program, erase or alter FPGA configuration, JTAG or SPI flash
  without exact owner authorization. Factory flash must be preserved.
- Raw Etherbone is unauthenticated trusted-LAN debug; never publish
  its port to an untrusted network.
- A source check, simulation, ISE vendor build, volatile FPGA load and
  real hardware observation are distinct proof levels. Do not
  substitute one for another.

## Branch lifecycle

Keep `main` as the reviewed source baseline. Use a short-lived
feature/review branch when helpful. No force push, reference deletion,
history rewrite or protected branch change without separate explicit
owner approval. The active laptop Git checkout and remote may be
different revisions during review; preserve both until alignment is
verified. Do not embed test history in the clean source recipe.
