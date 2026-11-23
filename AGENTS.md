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
4. GitHub hosts source, review and **selective CI**. CI is appropriate
   for fast deterministic unit tests, lint, static/security checks,
   clean-runner reproducibility and bounded PR gates. CI must **never**
   substitute for laptop rootless Docker, cgroups, private networking,
   authenticated MCP, licensed ISE or physical hardware acceptance.
5. Explore, debug and retry **locally without publishing**. Define the
   acceptance gate, verify the finished change in laptop containers,
   review the diff, then publish **one coherent commit at a working
   stopping point**; not a commit and push for every attempt.
6. Publish through the connected GitHub integration. Only use
   `repo_sync` if the clean laptop checkout has **shared ancestry**
   with the target branch. Do not reset an old `development` history
   onto unrelated `main` or silently force-update either side.
7. Record PASS/PENDING with the actual test machine, commands,
   results and limitations; source tests do not prove hardware.

## Local experimentation and commit quality gate

1. Before editing, specify the intended behavior and the smallest
   practical **local verification** that proves it. Work in `/workspace`,
   an isolated local checkout, or an approved disposable rootless test
   container. Keep experiments and temporary output off published refs.
2. Iterate through failures **without Git commits or pushes**. Preserve
   existing tunnel, broker, user data and persistent toolchain workers.
3. At a meaningful stopping point, run relevant laptop-local tests,
   inspect all changed files and private-data boundaries, and record
   confirmed PASS and separate PENDING gates. An untested change
   cannot be labeled verified; publishing a draft requires approval.
4. Only then make **one focused, descriptive commit and publication**
   for that complete logical change. Additional commits represent
   new independently verified progress, not repeated speculative
   fixes or CI retries. Local unpublished checkpoints are permitted.
5. If CI is specifically useful, state its purpose, supported
   environment, size/time budget and exact claim. A CI failure calls
   for local diagnosis and correction, **not a push-and-retry loop**.
   Do not introduce Actions workflows by default.
6. Keep unrelated laptop resources safe. The current clean main
   history and the laptop's older development checkout are unrelated;
   their reconciliation is separate from routine source publishing.

Read `docs/TESTING.md` and `docs/GIT_WORKFLOW.md` for the venue and
commit-decision checklists.

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
