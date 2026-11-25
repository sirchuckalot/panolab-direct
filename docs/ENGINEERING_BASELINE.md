# PanoLab Direct — Engineering Baseline / G2 Handoff

**Baseline date:** 2026-11-24
**Branch for engineering:** `development` in `sirchuckalot/panolab-direct`
**Frozen original software milestone:** `main` at `006b6ee` (LM1; do not advance implicitly)
**Authority:** This is a handoff index to tested evidence, recipes and open gates, not a new FPGA hardware release.

## Verified on the owner laptop

| Area | Evidence and supported scope |
| --- | --- |
| Rootless runtime / MCP | Owner-user rootless Docker, authenticated tunnel, Go manager, restricted repository gateway, Python Docker broker, and standalone modern dev container are operational |
| Current runtime topology | **Seven running**: tunnel, manager, repo-git, broker, modern development, persistent licensed ISE 14.7 worker, **temporary trusted-maintenance**; on-demand `setup` is stopped with restart policy `no` |
| Intended topology | **Six steady-state services** after temporary maintenance is retired: tunnel, manager, repo-git, broker, modern dev and persistent ISE worker; revised topology has **not** passed its own reboot/recovery test |
| Modern tools | One pinned Ubuntu development recipe; LiteX/Migen/LiteEth/LiteSPI and RISC-V/BIOS source builds and generic LiteX simulation were tested |
| Source selection | `projects/rescue/project.toml`, `shared/source_registry.py`, `third_party/registry.toml` and selected snapshot `files.sha256` records; **nine** source snapshots verified |
| Licensed FPGA compilation | Real Xilinx ISE 14.7 XST → NGDBuild → MAP → PAR → TRACE → BitGen completed on generic unconstrained Spartan-6 smoke fixtures |
| On-demand setup | Three stop/start cycles, 20 concurrent status probes, media inspection, invalid-install rejection, plus real licensed build **while setup was stopped** |
| Disposable vendor installation | **Two separate fresh ISE 14.7 installs**, on approved private media and scoped unattended terms acceptance, built genuine bitstreams, then disposed of their eight run-specific resources each; permanent license/installation preserved |
| Fresh-host admission | Read-only `panolab-install.sh --fresh-host-check` and empty-home diagnostic tested; **not** a real clean OS installation |
| Git source | Source, scripts, board/project definitions, test fixtures, Compose/Docker recipes, vendor-install automation, and applicable upstream notices belong in Git; vendor media, licenses, credentials and generated bitstreams do **not** |

Specific evidence: [LM1](../specs/LAB_MILESTONE_1.md),
[unified development image](UNIFIED_DEV_IMAGE_ACCEPTANCE.md),
[Rescue build](RESCUE_BUILD_EVIDENCE.md),
[ISE implementation](ISE14_REMOTE_BRINGUP_EVIDENCE.md),
[on-demand setup](ISE14_SETUP_ONDEMAND_STRESS.md),
[disposable ISE installation](ISE14_DISPOSABLE_INSTALL_ACCEPTANCE.md) and
[fresh-host limitations](FRESH_HOST_ACCEPTANCE.md).

## Rescue engineering stopping point

[Iteration-15 checkpoint](../projects/rescue/experiments/iteration-15/README.md): preserve the local experimental source and evidence; named read-only diagnostic ISE timing pass, 28 component/integration regression groups, later RAM-only simulation and independent ledger tests. No consolidated iteration-15 bitstream or physical Rescue boot. [Stock research](../research/pano-stock/README.md): one physical G2 Rev B, native Ethernet identity and 16 MiB SPI address-space backup; owner-private identity and binary remain outside Git. Next milestone is physical Rescue bring-up, not further speculative feature expansion.

## Authoritative source/configuration inventory

| Purpose | Canonical source |
| --- | --- |
| Ordinary-user entrypoint | `panolab-install.sh` → `host/rootless-install.sh`; read-only prerequisite inspection `host/fresh-host-audit.py` |
| Rootless Compose configuration | `docker/compose.setup.yaml`, `docker/compose.manage.yaml`, `host/compose.rootless-laptop.yaml`, and optional scoped Git-push overlay `docker/compose.git-push.yaml` |
| Modern HDL/LiteX tools | `docker/modern/Dockerfile`, `litex-bootstrap.py`, `litex-requirements.txt`, `litex-upstream.lock.json` |
| Normal MCP control plane | `docker/control/mcp/`, `docker/control/broker.py`, `ise_proxy.py`, `ise_setup.py`, `ise_staging.py`, `ise_acceptance.py`, `repo_gateway.py` and their Dockerfiles |
| Legacy vendor setup/worker | `docker/ise14/Dockerfile`, `entrypoint.sh`, `ise-system-edition.batch`, `mcp/main.go`, `mcp/setup/main.go` and tests |
| Authorized disposable acceptance | `docker/ise14/acceptance-policy.json`, `acceptance_build.json`, `acceptance_design.v`; the policy applies **only** to the exactly identified ISE 14.7 archive and known terms |
| Physical board BSP | `boards/pano_g2_rev_b/` |
| Rescue implementation | `projects/rescue/` (project manifest, SoC, firmware/BIOS overlay, tests and build entrypoints) |
| Shared and third-party source | `shared/`, `third_party/registry.toml`, individual `upstream.toml`, retained license texts and per-file SHA-256 manifests |
| Security/licensing | [Security boundaries](SECURITY.md), [source architecture](../specs/PANOLAB_SOURCE_AND_PROJECT_ARCHITECTURE.md), [license summary](../LICENSES/README.md) and original upstream notices |
| Git publishing | [Scoped development-branch push](GITHUB_PUBLISHING.md); `main` remains frozen |

**Not Git artifacts:** `docker/private/`, `docker/.env`, personal
tokens, Codex login state, node-locked license, proprietary Xilinx archive
and installed binaries, generated HDL/build directories, bitstreams and
private diagnostic traces. Local Docker image tags and backup containers
remain in the owner-user rootless Engine; committing sources does not
publish or serialize those images. The complete media/credential bootstrap
of a new host is **not** covered by a Git push.

## Present and deferred control planes

The normal authenticated manager/broker owns setup inspection, immutable
RTL staging, ISE builds, and the disposable `@ise-e2e` test end-to-end.
The **temporary trusted-maintenance sidecar remains enabled intentionally**
for fast owner-approved source review, recovery, image rebuild, and
stress-test debugging. Its broad rootless Docker-socket authority is an
explicit development exception, **not** the dependency of any accepted
normal-path installer/build test. Do not remove, narrow or relocate it
during this baseline cleanup; [the complete register](TEMPORARY_COMPONENTS.md)
defines future removal gates. Historical, revision-locked migration and
recovery scripts are preserved for provenance but **must not be rerun**.

## G2 development handoff (next phase)

The actual **Pano G2 Rev B** remains **unqualified** for Rescue programming. The later named diagnostic ISE timing pass and real stock discovery/backup are distinct evidence (see checkpoint above). The
working generic XC6SLX150 vendor bitstreams have no accepted board pin
constraints or hardware timing qualification. The next phase should start
with [G2 BSP](../boards/pano_g2_rev_b/README.md),
[Rescue project](../projects/rescue/README.md),
[Rescue implementation](RESCUE_IMPLEMENTATION.md) and the
[Rescue v1 safety standard](../specs/PANOLAB_RESCUE_V1.md); keep
CPU-less Etherbone application and CPU-equipped Rescue personalities
separate. Board pinout, clock/PHY, Etherbone/CSR behavior, timing closure,
independent recovery and any physical programming all require their
own evidence and explicit owner approval.

## Still pending — not release blockers for the *development baseline*

- A genuinely unprovisioned, independent Linux laptop/VM installation,
  including host packages, rootless Engine, private inputs and user login.
- Cold reboot acceptance of the revised setup-on-demand/temporary-sidecar
  topology, plus the proposed six-service hardened configuration.
- Permanent restricted/self-recovering management replacement and retirement
  of the broad temporary sidecar.
- Independent, full redistribution audit of source licenses and generated
  hardware artifacts; upstream source keeps its original license, **never**
  a blanket top-level relicense.
- Physical Pano G2 bitstream qualification, Etherbone connectivity,
  programmed-board recovery, flash and A/B application updates.

## Baseline verification and publication

Use `docs/DEVELOPMENT.md` for source and test commands. Qualification
requires a clean `development` checkout, verified source registry,
reviewed local tests, checked Markdown links/secret exclusions, and a
**non-force push of the reviewed development HEAD**. Verify the remote
commit after push. Publish **source only**. Neither GitHub Actions nor
a successful generic ISE build can establish a physical-board PASS.

Dated historical records remain in `docs/` and `specs/`, with their
original measurements and stage-specific limitations preserved. Refer
to this handoff for the *current* status rather than treating the
earlier six-container or eight-container reports as current topology.
