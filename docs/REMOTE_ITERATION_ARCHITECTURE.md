# PanoLab Direct: remote-first iteration architecture

Historical remote bring-up design and evidence. See [architecture](ARCHITECTURE.md) for the current deployment and retirement requirements.

**Status:** Architecture decision with live remote acceptance evidence
(2026-11-24). The owner-approved temporary management bootstrap, authenticated
ISE MCP tools, immutable source staging and a real licensed six-stage
Spartan-6 bitstream build have passed on the rootless laptop. See
[the verified vendor evidence](EVIDENCE.md#licensed-ise-bring-up).
The permanent self-upgrade controller and board-specific hardware acceptance
are still outstanding. No FPGA programming was performed.

## Runtime service count: tested on-demand setup, proposed steady six

The first accepted, pre-ISE laboratory ran six containers; early ISE
development used eight, including an always-running `setup` and temporary
`trusted-maintenance`. The later
[on-demand setup stress test](EVIDENCE.md#on-demand-ise-setup) demonstrated
three normal-MCP stop/start cycles, 20 concurrent status probes, a full
vendor-media inspection, and a genuine six-stage licensed implementation
while `setup` was stopped. The installer now has an opt-in
`ise-setup` Compose profile and `restart: no`. Manager/tunnel setup
startup dependencies have been removed. The active engineering
configuration is now **seven** containers: six regular laboratory roles
plus the separate temporary maintenance sidecar.

The **proposed six-service steady-state topology** remains
`tunnel`, `manager`, `docker-broker`, `repo-git`,
`dev` and persistent licensed `ise-worker`. It requires retiring
`trusted-maintenance` after a bounded remote update/recovery mechanism
has been independently accepted. Full reboot recovery, first-time setup
provisioning if no setup container exists, and clean installation from
an unprovisioned host remain distinct acceptance gates. The target
six-service topology is **not yet reboot-qualified**.

## Normal-path disposable ISE installation acceptance

A separate [disposable installation acceptance controller](ISE14_DISPOSABLE_INSTALL_ACCEPTANCE.md)
has now proved a genuine fresh ISE 14.7 System Edition installation and
six-stage licensed Spartan-6 compilation using the **normal authenticated
manager → rootless Docker broker** path. The normal `@ise-e2e` compatibility
interface creates uniquely labeled, private setup/worker containers, a
Docker-internal licensed network, and five independent named volumes.
It verifies the exact approved vendor archive SHA-256 and the owner's
package-scoped unattended EULA authorization, stages an unconstrained RTL
fixture, checks the generated bitstream/report hashes, and disposes of
all eight run-specific resources while retaining only private summary
evidence. No installed vendor volume, original license, persistent worker,
or existing on-demand setup state is modified.

This is a test/commissioning capability outside the temporary
`trusted-maintenance` route. That sidecar was used only to review
candidate source, correct the live broker registration, and inspect
installation progress; it never executed the acceptance workflow.
This test does **not** claim a new laptop's Docker, Git, or private-media
provisioning is automated, nor does it qualify any Pano G2 hardware pinout.
The exact accepted result IDs and hashes are recorded in the linked evidence.

## Temporary owner-trusted remote maintenance bootstrap

**Temporary implementation activated and independently tested.** To eliminate repeated
laptop terminal sessions while the engineering control plane is still under
construction, the candidate deployment provides an explicit
`trusted-maintenance` Compose profile and a persistent
`panolab-direct-trusted-maintenance` helper. This sidecar mounts the
**owner's rootless Docker socket** and the canonical repository read-only,
with the approved agent workspace writable; it has no network namespace
access and never requires `sudo` or rootful Docker.

This is a substantial, deliberate trust expansion: **access to the rootless
Docker socket is effectively control of the laptop owner's containers and
user-accessible mounted files**. Read-only source mounts do not neutralize
that authority. This is permitted only as a temporary, owner-approved
development bootstrap. The authenticated MCP connection is the sole normal
remote entry point; the sidecar does not expose a public listening port.

When enabled, `dev_exec` with `Argv` beginning `@maintenance` passes
the remaining argument vector into the **fixed named maintenance sidecar**,
after verifying its Compose identity, running state, offline network mode
and nonprivileged Docker environment. Example: `["@maintenance",
"docker", "ps"]`. Commands intentionally have broad owner-user Docker
authority in this temporary mode. Don't accept arbitrary untrusted
instructions through this interface.

The broker uses one read-only **directory** bind of `docker/control/`
and starts `broker.py` from that directory. This replaces the original
individual file binds, which pinned old inodes after atomic source writes.
Repository updates now become visible to Python module reloads without
rebuilding images. ISE adapter modules are
reloaded on each request, and broker-main Python edits take effect after a
remote-only broker restart. The **Go manager and Go ISE worker are compiled
executables**, so they still need a build to turn source changes into
runnable binaries. The trusted maintenance sidecar has Docker CLI/Compose
to execute those builds and container swaps *remotely*, without another
owner-run activation script. Source and builds remain separate.

The [external-storage cutover candidate](EXTERNAL_STORAGE_CUTOVER.md) keeps
the broker's live `docker/control/` bind and gives the development container
one read-only canonical checkout at `/repo`, with `/repo/.git` masked by
read-only tmpfs. The workspace comes from `PANOLAB_DATA_DIR/agent-workspace`
and Codex authentication from `PANOLAB_CONFIG_DIR/codex-auth` on dedicated
writable mounts. The Git gateway uses the canonical checkout and a separate
data-root RPC directory. Its optional Git push credential is a dedicated
read-only bind from the configuration root. The legacy checkout-local
private paths still belong to the running baseline until owner-local cutover
and runtime verification.

The live-mounted `host/trusted-maintenance.sh` implements:

- `status` and `check` for rootless Docker and MCP health
- `reload-broker` for a Python-source-only restart
- `deploy-management` for separate candidate-image builds, Go unit tests,
  saved-image tags, and rollback if the authenticated maintenance canary fails

For a broker/manager restart, invoke the maintenance script detached within
the sidecar (using its Docker socket) so the remote caller can disconnect
without killing the ongoing upgrade. Results are stored in
`/workspace/maintenance/status.json` and
`/workspace/maintenance/latest.log`; the normal remote workspace tools can
inspect them after reconnection.

**Shutdown/removal after acceptance:** Stop and disable the
`trusted-maintenance` Compose profile, remove the broker `@maintenance`
compatibility route and the `PANOLAB_TRUSTED_MAINTENANCE` switch, and remove
the temporary broker code bind mounts. Replace them with a narrowly scoped,
reviewed, independently recoverable release controller. Stopping the
sidecar alone blocks the remote commands but is **not** a complete removal
of its source/deployment configuration. Do not describe the setup as
production-hardened until this cleanup is independently verified.

## Problem and evidence

The 2026-11-24 initial bring-up installed ISE 14.7 but repeatedly required
local terminal commands to promote manager/broker source. The authenticated
remote interface and trusted maintenance sidecar now support remote
container recovery, while the project staging operation gives the worker
immutable source revisions without vendor-image rebuilds. An important
license regression was also identified and repaired: the old
`--network none` worker had no Ethernet interface to match a node-locked
Xilinx license. The current worker uses an exclusively internal Docker
network with the existing licensed virtual Ethernet identity; genuine MAP,
PAR, TRACE and BitGen subsequently passed. No external vendor network port
or FPGA programming path was enabled.

One attempted bridge deployment also rolled back because its health probe
used `python3 -c 'import ise_proxy'`, without the module directory on the
Python path. The file was present at `/usr/local/bin/ise_proxy.py`; this was
a false-negative probe, not evidence that broker image construction failed.

## Decisions

**Target architecture: keep a small immutable, authenticated control plane.**
The MCP manager,
rootless-Docker broker, credential boundaries, worker identity/mount checks,
hardware-programming gates, and operation allowlists must not be hot-reloaded
from agent-writable source. They have broad indirect authority over the
owner's rootless Docker environment. Changing these security-critical
components requires tests, versioned promotion, health checks, and rollback.
The temporary owner-trusted development bootstrap is an explicitly accepted
exception to this production target: its mounted broker code has indirect
access to the owner's rootless Docker socket. Retire this exception after
commissioning. The Go manager is a compiled binary, not a Python script
that can be refreshed merely by mounting Go source.

**Make normal FPGA development data live-mounted and remotely staged.** Keep
the persistent ISE 14.7 vendor worker and its five canonical MCP operations
(`toolchain_info`, `build_start`, `build_status`, `build_result`,
`build_cancel`). Support a stable, restricted interface for authorized
remote clients to stage Verilog, UCF, and `build.json` into an isolated
project input area. Use checked regular files, approved project IDs and part
numbers, bounded sizes, atomic revisions, and content hashes. The worker
sees approved input revisions read-only; output remains in per-job private
results. A fresh job snapshots and records input hashes so changes during
a build cannot alter that job's authoritative inputs. New project revisions
need neither a new vendor image nor a worker restart.

**Separate three distinct change classes.**

| Change | Normal update |
| --- | --- |
| RTL, UCF, source-to-RTL build outputs, project manifests and tests | Agent updates the approved source/workspace; validates and stages a new immutable worker-input revision; starts a new build remotely |
| Nonprivileged diagnostic adapters and project-local scripts | Agent edits a mounted, unprivileged staging workspace; bounded tests and per-job execution; no access to Docker socket or license |
| Manager/broker code, authentication, tool authorization, Docker policy or vendor-runtime binary | Versioned candidate image or binary; offline tests; explicit verified promotion and rollback (not a blanket hot mount) |

**Use the outbound MCP control plane for steady-state operation.** The
remote control path must expose only typed operations for project staging,
worker status, build start/status/result/cancel, and safe log categories or
bounded redacted diagnostics. A user should not be a terminal relay for
routine builds, failing tests, job inspection, artifact hashes or
configuration changes. The first activation of a new management capability
may require owner-run bootstrap when the existing control plane lacks that
capability. Once bootstrapped, routine source iterations require no laptop
terminal access.

**Remote lifecycle and safety.** Future management upgrades should be
staged as content-addressed, versioned releases with preflight checks,
canary acceptance, an independent rollback decision, and a known-good
control-plane fallback. Design the upgrade mechanism without a general
remote shell, arbitrary Docker commands, or an agent-writable script running
with Docker-socket access. Keep initial activation/local recovery as the
break-glass path, not the day-to-day workflow.

## Proposed target data flow

```text
Git development + board BSP + upstream snapshot registry
                   |
                   v
       rootless modern dev container
       (read-only repo; writable build workspace)
                   |
                   v
       controlled staging / validation
       (approved file types, size, hash, atomic revision)
                   |
                   v
       ISE worker: read-only /projects/<id>/<revision>
           XST -> NGDBuild -> MAP -> PAR -> TRACE -> BitGen
                   |
                   v
       private per-job results and hashes
                   |
                   v
        authenticated MCP job/result access
```

The licensed vendor installation and license input remain private and
read-only in the worker; neither is present in the modern development
container or uploaded to GitHub. A remote build does not authorize JTAG,
SPI flash, or FPGA programming.

## Acceptance plan

1. **Bootstrap bridge:** Fix the broker's false-negative module import probe,
   promote only the tested manager/broker candidate, prove authenticated
   worker diagnostics and preserve a recoverable previous image. This stage
   **Accepted on the laptop:** authenticated remote bridge and maintenance
   canaries passed, with prior images/worker preserved as recoverable copies.
2. **First real vendor build:** Diagnose `build_start`, verify actual ISE
   license checkout and all six implementation stages, and record a
   nonempty bitstream, reports, job manifest and SHA-256. **Accepted for
   generic, unconstrained XC6SLX150 vendor toolchain smoke testing:**
   job `1795535626519203841`, bitstream 4,220,305 bytes, six stages passed.
3. **Remote iteration:** Activate the candidate staging operation,
   `ise_project_stage` (also compatible with `@ise14 stage <project>`).
   The source is `/workspace/ise-staging/<project>/build.json`, its declared
   Verilog and UCF files. The broker uses a temporary networkless helper to
   snapshot them into the worker's existing read-only `/projects` mount as
   `<project>-<sha256-prefix>`. Remotely edit a safe smoke design twice,
   stage and build immutable versions without rebuilding/restarting
   any existing container, and verify the two full input hashes.
   **Accepted on the real rootless laptop:** two immutable Verilog source
   revisions compiled independently through all six licensed ISE stages
   without rebuilding or restarting the vendor worker. Both generated
   nonempty, differently hashed bitstreams. See
   [the real build evidence](EVIDENCE.md#licensed-ise-bring-up).
4. **Recovery:** Test malformed source rejection, stage rollback, active
   build cancellation, worker restart persistence, invalid request denial,
   source race resistance and preservation of the existing secure tunnel.
5. **Remote management evolution:** Design a bounded, independently
   recoverable update controller for infrequent control-plane releases.
   Review its Docker-socket authority separately before enabling it.

Do not mark steps 1-5 passed based on unit tests alone. Record live laptop
evidence and link it from the operating architecture after acceptance.

This is consistent with
[the source/project standard](../specs/PANOLAB_SOURCE_AND_PROJECT_ARCHITECTURE.md),
[the canonical worker contract](TOOLCHAIN_MCP_CONTRACT.md) and
[the existing security boundary](SECURITY.md).
