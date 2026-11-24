# ISE 14.7 remote milestone — source review and preservation (2026-11-24)

**Purpose:** Preserve the verified remote-first FPGA development laboratory and
identify which engineering changes are durable versus explicitly temporary.
This records the **25 source paths that were modified/untracked at the start
of this checkpoint review**. README and operational documentation reconciliation
is additional to those 25 paths.

## Live acceptance and provenance

- Branch at review start: `development`, HEAD
  `3286ab33b76885ce6b5c367b922c5d8f39601039`; the starting
  25 paths were reviewed before committing.
- Eight active service/development/ISE containers were observed on the laptop;
  **eight is the temporary active engineering configuration, not a chosen
  final appliance service count**. The earlier accepted baseline used six.
  A proposed six-service steady state keeps tunnel, manager, docker-broker,
  repo-git, modern dev and the licensed ISE worker; it would retire the
  trusted-maintenance sidecar and make ISE setup **commissioning/on-demand**
  instead of permanently running. This proposed topology requires explicit
  Compose dependency and restart tests before acceptance. Two earlier ISE
  worker rollback containers were retained stopped.
  No services were intentionally recreated or pruned during the checkpoint.
- Vendor job `1795535626519203841` succeeded, exit 0. Its actual
  `design.bit` is 4,220,305 bytes with SHA-256
  `2d80c633d3e4915a65308fd58ff39828b8d3d4dd475ee244a2d2fef2aa11f1f9`.
- A **different immutable RTL revision** produced a second genuine successful
  six-stage job `1795535788871331709`, exit 0, separate bitstream hash
  `da710d59aa60d5e9806bcc83e2ce82c9d2d38f549090ecd13f996ead7bce8bac`.
  Neither bitstream is approved for real board programming.
- The owner-supplied node-locked Xilinx license is kept private and unmodified.
  The ISE worker uses a single, Docker-**internal** virtual network with the
  existing licensed Ethernet identity, no externally published vendor port,
  rootless Engine, dropped capabilities and read-only license mount.
- The actual source control checkpoint is not a Docker image snapshot.
  Existing running images are separately preserved with explicit Docker
  tags (below); the licensing/vendor data and job evidence remain in ignored
  owner-private paths.

## Review of the original 25 changed paths

**Durable engineering functionality and tests (16 paths):**

| Source path | Accepted role |
| --- | --- |
| `docker/control/Broker.Dockerfile` | Build-tested broker bundle for typed ISE/staging adapter and Python contract tests; also includes temporary bridge test |
| `docker/control/mcp/main.go` | Register the authenticated ISE manager tools |
| `docker/control/mcp/setup_proxy.go` | Correct cancellation precedence in setup HTTP proxy |
| `docker/control/mcp/setup_proxy_test.go` | Pre-cancel and in-flight cancellation regressions |
| `docker/ise14/entrypoint.sh` | Rootless worker startup without user creation, setuid or host chown |
| `docker/ise14/mcp/main.go` | Pin six real vendor executables to validated absolute paths |
| `docker/ise14/mcp/main_test.go` | Verify vendor executable allowlist |
| `docker/ise14/mcp/setup/main.go` | Extract vendor media without restoring unsupported UID/GID ownership |
| `docker/control/ise_proxy.py` | Validate worker identity/network/mounts; translate MCP request keys and redact diagnostics |
| `docker/control/ise_staging.py` | Bounded atomic, content-hashed immutable project staging |
| `docker/control/mcp/ise_proxy.go` | Explicit manager ISE job/staging/diagnostic tool API |
| `docker/control/test_ise_proxy.py` | Worker-security, protocol, redaction and internal-network tests |
| `docker/control/test_ise_staging.py` | Stage idempotence, source isolation and invalid-file/mount rejection |
| `docker/ise14/mcp/setup/main_test.go` | Rootless tar extraction regression |
| `host/ise14-bringup.py` | Owner-only installer/smoke driver; now checks clean committed source for installer mutation and uses lowercase MCP fields |
| `host/ise14-diagnose.py` | Read-only, redacted vendor-install diagnosis |

**Hybrid source containing durable operations AND temporary access (2 paths):**

| Source path | Boundary |
| --- | --- |
| `docker/control/broker.py` | Durable ISE validation/staging, plus temporary broad `@maintenance` bypass through the owner's rootless Docker sidecar |
| `docker/compose.manage.yaml` | Existing long-lived services plus temporary broker live-directory bind and `trusted-maintenance` profile |

**Temporary/one-time operations to retire or archive (5 paths):**

| Source path | Retirement guidance |
| --- | --- |
| `docker/control/Maintenance.Dockerfile` | Remove with the broad temporary maintenance profile after a bounded updater is proven |
| `docker/control/test_trusted_maintenance.py` | Retain while `@maintenance` is enabled; remove/update when its temporary route is retired |
| `host/activate-ise-bridge.sh` | **Historical one-time bootstrap** tied to a previous commit/dirty-file inventory. **Do not rerun** against this committed milestone |
| `host/ise14-repair.py` | **Historical one-time tar-failure repair** for the 2026-11-24 failed-install state. Do not rerun on the successful installation |
| `host/trusted-maintenance.sh` | Temporary rootless sidecar control script; replacement must retain remote rollback and authenticated canaries |

**Permanent engineering evidence and decisions (2 paths):**

| Document | Role |
| --- | --- |
| `docs/ISE14_REMOTE_BRINGUP_EVIDENCE.md` | Genuine six-stage job history, license regression/root cause, artifact SHA-256, immutable revisions |
| `docs/REMOTE_ITERATION_ARCHITECTURE.md` | Long-term split of live FPGA project inputs versus protected management binaries; temporary trust exception |

This classification concerns **the 25 starting paths**, not a claim that all
temporary software is production-approved. It is intentionally included in
the development checkpoint so we can reproduce and safely remove it later.

## Documentation reconciled during review

- `README.md`: the six-service LM1 history remains historically accurate;
  the current eight-container lab and **two licensed bitstream builds** are
  now shown separately. Links point to the current evidence and risks.
- `docs/ARCHITECTURE.md`: distinguishes the original six-service
  acceptance from the expanded remote-managed ISE laboratory.
- `docs/GETTING_STARTED.md`: records current services, temp `@maintenance`
  access and outstanding fresh-install/reboot qualification.
- `docs/SECURITY.md`: explicitly discloses the additional rootless Docker
  socket exposure to the trusted sidecar and keeps board programming gated.
- `docs/TOOLCHAIN_MCP_CONTRACT.md`: retains **five canonical worker tools**;
  distinguishes separate manager staging/diagnostic adapters and documents
  the accepted vendor implementation.

## Checkpointed images and rollback evidence

The following image tags reference the **exact images used by the running
containers** at this checkpoint, rather than arbitrary latest builds:

| Service | Preserved Docker image tag |
| --- | --- |
| Broker | `panolab-direct-broker:checkpoint-20261124` |
| MCP manager | `panolab-direct-manager:checkpoint-20261124` |
| Trusted maintenance | `panolab-direct-trusted-maintenance:checkpoint-20261124` |
| ISE setup | `panolab-direct-ise14-setup:checkpoint-20261124` |
| Modern development | `panolab-direct-modern:checkpoint-20261124` |
| Licensed ISE worker | `panolab-direct-ise14-worker:checkpoint-20261124` |
| Pre-absolute-path-fix worker | `panolab-direct-ise14-worker:pre-absolute-path-fix-20261124` |

The stopped containers
`panolab-direct-ise14-worker-backup-network-none-20261124` and
`panolab-direct-ise14-worker-backup-absbin-20261124` were retained.
Do not remove or restart these as part of ordinary source publishing.
A private, machine-readable container/image-ID inventory is stored in the
owner's `agent-workspace/maintenance/checkpoint-20261124-images-and-rollbacks.json`.
Private license, archive, bearer, vendor logs, job directories and bitstreams
remain outside Git.

## Checkpoint test boundaries

Accepted evidence includes:
- Two real six-stage vendor builds with exit code zero, source identity,
  separate implementation reports, and distinct bitstream SHA-256 values.
- A fresh read of eight running services and an internal-only license network.
- Build-time tests of candidate manager, broker, ISE worker and ISE setup
  image targets **without swapping running services**.
- Python proxy and staging regression tests; Bash/Python syntax checks,
  Compose validation and Git whitespace/no-private-path review.

No tests here should be interpreted as a clean unprovisioned-machine install,
new eight-container reboot acceptance, license portability to another host,
G2 Rev B board-constraint qualification, timing closure of a real G2 design,
or physical FPGA programming.

## Retirement/recovery next steps

1. Review and commit the source-only checkpoint to `development`; keep
   `main` and remote GitHub unchanged unless separately authorized.
2. First reboot-test the **currently running eight-container engineering**
   configuration and verify licensed MAC, private mounts, authenticated MCP
   and a fresh six-stage source build; this does not promote eight as final.
   Then validate the **proposed six-service steady state** separately,
   removing the temporary sidecar and making setup an on-demand service.
   The current `manager` Compose `depends_on: setup` must be redesigned
   and tested before setup can be retired from the steady state.
3. Review fresh-host installer reproducibility. The original one-time
   `activate-ise-bridge.sh` and `ise14-repair.py` are **not** a
   production installer and their old source revision guards must not be
   reused as a generic recovery path.
4. Implement a narrowly authorized remote updater with independent
   rollback; after acceptance disable the trusted sidecar, remove the
   broad broker action and live-mounted broker policy source, and check
   that Docker-socket access is narrowed again.
5. Continue G2-specific BSP/constraints integration, simulation and
   genuine vendor implementation. Do not program a board without
   independent owner authorization and recovery qualification.
