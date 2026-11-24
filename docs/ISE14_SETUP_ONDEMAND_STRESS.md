# ISE 14.7 setup on-demand acceptance / stress test — 2026-11-24

**Scope:** Verify that the already-installed Xilinx ISE 14.7 setup service
can be parked until commissioning or repair is needed, restarted through the
regular authenticated PanoLab MCP interface, and stopped again **without
using the temporary maintenance sidecar as a test executor**. Preserve
all vendor files, credentials, running workers and rollback evidence.

## Result

**PASS for an existing, previously provisioned setup container.**
The optional `ise-setup` Compose profile, removed manager/tunnel setup
dependencies and `restart: no` were checked against the actual rootless
Compose configuration. The existing setup service was exercised using
regular `lab_lifecycle` and the new restricted `@setup` compatibility
route. The regular `@ise14` interface completed a fresh licensed six-stage
vendor implementation while setup was stopped.

**NOT accepted as a completely self-provisioning, fresh-host on-demand
installer.** The current normal `lab_lifecycle start` operation requires a
pre-existing stopped setup container. If that container has been deleted,
`@setup` reports `not_created`, but no ordinary MCP setup-creation
operation exists yet. A clean-host installer/bootstrap path and full laptop
reboot recovery require separate tests.

## Runtime source changes

- `docker/compose.setup.yaml`: `setup` now declares
  `profiles: ["ise-setup"]` and `restart: "no"`.
  The base tunnel no longer depends on setup.
- `docker/compose.manage.yaml`: the manager's `depends_on: setup`
  edge is removed. It still depends on broker and repo-git.
- The already-present setup container was updated to restart policy
  `no` without being deleted or reinstalled; source-level Compose
  changes alone do not alter a container's existing restart policy.
- `docker/control/ise_setup.py` and the normal broker `@setup`
  inspection route call the **existing manager → setup MCP proxy**.
  They accept only `info`, `status`, `inspect`, and
  `reject_invalid_install`; no real installer-start operation is
  reachable through this route.
- `docker/control/test_ise_setup.py` covers identity validation,
  negative permissions, offline/missing states, read-only fields and
  the normal broker dispatch. `Broker.Dockerfile` embeds the new module
  and its tests for reproducibility.

### Source and Compose validation

Rootless Compose rendering returned:

| Selection | Services selected |
| --- | --- |
| No optional profiles | `docker-broker`, `manager`, `repo-git`, `tunnel` |
| `--profile ise-setup` | The four above **plus `setup`** |
| `--profile trusted-maintenance` | The four above **plus temporary maintenance**, without setup |

The modern developer and licensed ISE worker are separate persistent
containers, not additional Compose services. Thus, when setup is off,
the present engineering lab has **seven active containers** (the six
proposed steady-state roles plus the *temporary* maintenance sidecar).
The final six-service topology remains a **target**, not a reboot-
qualified or security-hardened release.

## Normal-route live stress evidence

All functional probes below ran through the existing PanoLab authenticated
MCP connection: `lab_lifecycle`, `lab_status`, `@setup` or `@ise14`.
No test called `@maintenance` to execute setup MCP requests or control
setup service start/stop. The maintenance sidecar was used only for
**source review, corrective broker restart, restart-policy update,
candidate image builds and read-only private-file integrity review**.

| Probe | Observed evidence | Result |
| --- | --- | --- |
| Setup stopped | `@setup status` and `@setup info` returned `available:false,state:stopped` | PASS |
| Setup started by normal lifecycle | `@setup info`: installed, archive, license present, Docker socket absent | PASS |
| Persisted installer state | `@setup status`: `install_state:succeeded`, no failure details | PASS |
| Media inspect via authenticated proxy | Archive 6,538,618,880 bytes; SHA-256 `cee0b046c1bbcfafcae59a96c7596c55c5477628c39bafefff8992cb8d33adaa` | PASS |
| Invalid installer command | Invalid confirmation was refused before installation | PASS |
| Unauthorized request types | `@setup install`, `reinstall`, `shell` all refused | PASS |
| Concurrent status calls | 20/20 `@setup status` returned `succeeded` | PASS |
| Concurrent batch elapsed time | Approximately 30.8 seconds due to serialized broker request handling | PERFORMANCE LIMIT |
| Repeated stop/start | Three full stop → offline → worker health → start → succeeded cycles | PASS |
| Post-policy on-demand start/stop | One additional round trip after applying `restart:no` | PASS |
| Setup fully offline | Manager, tunnel, licensed worker and normal MCP remained operational | PASS |
| Fresh real licensed build with setup stopped | Job `1795542077281586637`, state `succeeded`, exit `0` | PASS |
| Six implementation stages | Separate XST, NGDBuild, MAP, PAR, TRACE and BitGen artifacts | PASS |
| Generated bitstream | `design.bit` 4,220,305 bytes, SHA-256 `f0ad3f96557a41ba5e994982e929c98b3c393e1ec61d7ee7a0cfe1516bcbfab7` | PASS |
| Timing report | `design.twr` returned as implementation artifact | PASS |
| Private file integrity | License, successful installer state and ISE settings SHA-256 unchanged against pretest snapshot | PASS |
| Final setup state | Stopped, `restart:no`; normal `@setup status` returns `state:stopped` | PASS |

The test used the previously staged, generic `XC6SLX150` RTL smoke
design; it is not a board-qualified Pano G2 programming image.
No JTAG, FPGA programming, flash write, vendor reinstall, license edit,
network-identity change, or destructive cleanup was performed.

## Source/build review (not a substitute for live tests)

- Ten Python setup-contract and broker-dispatch unit tests passed
  inside the ordinary development container.
- Current Compose source passed syntax/topology checks and rootless
  `docker compose config --services` evaluation.
- Candidate broker and setup images built with their embedded tests,
  without replacing running image tags/containers.
- The manager Go setup-proxy/cancellation tests passed in a separate
  candidate manager image, without deploying it.
- The first candidate broker build identified a test-fixture path issue
  (`/tmp/broker.py` versus installed `/usr/local/bin/panolab-broker.py`).
  The test path was fixed; the next candidate build and tests passed.
- All stopped ISE worker backup containers and checkpointed images were
  left intact.

## Remaining acceptance gates

1. **Provision from absence:** implement a narrowly typed, authenticated
   create/prepare operation for setup when the container does not yet
   exist, or demonstrate that the one-command commissioning installer
   reliably pre-creates it. Do not depend on `@maintenance` for normal
   on-demand recovery.
2. **Cold reboot:** check rootless Engine startup, manager/tunnel availability,
   the setup container remaining off, and licensed ISE build correctness
   after an actual host reboot. No laptop reboot was requested/performed.
3. **Installer destructive path:** reinstallation/extraction from scratch
   was intentionally *not* exercised on the working licensed host.
   Test this in a separate disposable environment with appropriately
   authorized media, without copying private keys into source control.
4. **Temporary bridge retirement:** independently qualify a bounded
   remote update/recovery controller before disabling the trusted
   maintenance sidecar. The presence of that sidecar is the remaining
   additional active container relative to the proposed six.
5. **Performance:** remove the one-lock broker serialization bottleneck
   for safe read-only setup status requests, while maintaining validation,
   cancellation and secret non-disclosure.
6. **Board qualification:** physical Pano G2 Rev B constraints/timing/
   programming remain separate approval gates.

## Recommended normal operations

For the **existing, pre-provisioned** setup container:

- Inspect: `@setup status` — reports available or stopped.
- Bring online: authenticated `lab_lifecycle` with
  `Container=panolab-direct-connect-setup-1`,
  `Operation=start`.
- Read only: `@setup info`, `@setup status`, or `@setup inspect`.
- Stop when finished: authenticated `lab_lifecycle` with
  `Operation=stop`.

Do not rerun the historic one-time `host/ise14-repair.py` or
`host/activate-ise-bridge.sh` scripts on the accepted installation.
Real vendor installation still requires separate owner authorization,
explicit licensing terms acceptance and checksum validation.

Related documents:
[remote architecture](REMOTE_ITERATION_ARCHITECTURE.md),
[ISE implementation evidence](ISE14_REMOTE_BRINGUP_EVIDENCE.md),
[previous milestone review](ISE14_REMOTE_MILESTONE_REVIEW.md).


## Follow-up — fresh disposable vendor installation (2026-11-24)

A separate [normal-MCP disposable acceptance controller](ISE14_DISPOSABLE_INSTALL_ACCEPTANCE.md)
now **passed twice**: each run created its own setup container and empty
vendor installation/work volumes, verified the owner-authorized archive
SHA-256, installed ISE 14.7 unattended, started an isolated licensed
worker, built a real Spartan-6 bitstream and timing report, and deleted
all eight test-specific Docker resources. Neither run executed through
temporary maintenance. The original installed vendor files and license
were independently confirmed unchanged.

This closes the **disposable vendor-install-from-empty-volume** acceptance
gap, not the entire clean-host appliance setup. The normal `@setup`
operation still cannot recreate the *persistent named setup service*
if that service was deleted, and current acceptance preflight still
uses known-good image tags and the existing normal setup container to
resolve the approved private media mounts. A completely unprovisioned
laptop and cold reboot remain separate acceptance targets.
