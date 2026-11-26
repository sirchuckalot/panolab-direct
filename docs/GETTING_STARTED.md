# Install and operate the rootless laptop laboratory

This describes the **current supported deployment recipe** and its
explicit prerequisites. Read the [operating baseline](ARCHITECTURE.md)
for current acceptance results and the
[host script index](../host/README.md) before running an old helper.
The installer does not perform host Docker installation and has not
been validated as an unattended fresh-machine install.

## 1. Host prerequisites

Use an ordinary non-root user on Linux x86_64 with Git, Bash,
Python 3, Docker CLI/Compose and **Buildx**, and an already provisioned **rootless
Docker Engine** with systemd cgroups v2 and CPU/memory/PID delegation.
The laptop installation uses the preprovisioned user helper at
`~/.local/libexec/panolab-rootless-29.1.3/dockerd-rootless.sh`.
If a different host lacks this helper or delegated resources,
**stop and review the prerequisite**; do not silently run `sudo`,
host `apt` or a nested/rootful Docker daemon.

Containerized tooling includes Python, Git, Yosys, Icarus, Verilator,
Codex and the [pinned LiteX/VexRiscv Rescue stack](#verify-the-pinned-litex-environment):
LiteX BIOS, LiteX-Boards, LiteEth, LiteSPI, Migen, SPI/PHY support,
RISC-V GCC/binutils, Meson/Ninja and simulation C libraries.
Licensed ISE remains separately approved. **Host Docker Buildx** is a
Docker CLI extension (not another Docker image or development service).
For the owner-laptop version-pinned, no-sudo bootstrap and exact
old-development-rollback cleanup, see the
[toolchain cleanup procedure](#buildx-and-the-guarded-rollback-cleanup).
The installer now builds images with BuildKit and fails rather than
falling back to Docker's deprecated legacy builder.

### Clean-host prerequisite admission

Use `bash ./panolab-install.sh --fresh-host-check` before attempting
an installation on a new host. This **read-only** check reports missing
Docker/Compose/Buildx, rootless/user-session/cgroup requirements,
subordinate UID/GID mappings, checkout identity and private-input
presence. It does not start services, provision operating-system packages,
download vendor media, read secret values or accept license terms.
A missing-prerequisite report returns exit code `10`; even a `READY`
report establishes **prerequisite readiness only**, not a working
installation. A genuinely new host may require a reviewed OS
administrator provisioning step and owner-provided private media.
Read [the actual test and remaining gates](EVIDENCE.md#fresh-host-admission).

### Independent fresh-host qualification

1. Launch an **independent disposable Linux x86_64 VM/host** with a
   known OS image and confirmed owner approval for first-time OS setup;
   it must not share the working laptop's Docker images, volumes,
   Git checkout or secret directories.
2. Record the clean baseline, rootless prerequisites, image/cache
   state and absence of PanoLab services. Run
   `bash panolab-install.sh --fresh-host-check` and record all blockers.
3. Establish the host runtime explicitly and safely. If system packages,
   uidmap or kernel changes are required, handle them through a reviewed
   OS provisioning step, never through the temporary PanoLab sidecar.
4. Provide private owner-approved credentials and media through
   a separate encrypted input channel or already-authorized local
   facility. Validate exact vendor SHA-256 and licensing scope; do not
   send credentials/media to a public CI runner.
5. Run the **normal one-command launcher** and make it build the manager,
   broker, repo gateway, modern tools, optional setup and licensed
   worker from reviewed source. Validate typed lifecycle, authenticated
   remote MCP, resource limits and setup-off-by-default behavior.
6. Run `@ise-e2e start` from the **normal MCP route**, wait for
   `passed` + `disposed:true`, verify all six vendor stages, artifact
   hashes and strict cleanup.
7. Exercise a persistent installed worker, reboot the independent host
   and confirm automatic return of the intended six services. Keep
   temporary maintenance absent for the entire acceptance execution.
8. Preserve the evidence/known-good versions and destroy **only the
   independent clean-host test environment** after qualification.

## 2. Owner-private inputs

Provision two separate owner-owned mode 0700 directories outside the
checkout. The defaults are `${XDG_CONFIG_HOME:-$HOME/.config}/panolab`
and `${XDG_DATA_HOME:-$HOME/.local/share}/panolab`. Use
`PANOLAB_CONFIG_DIR` and `PANOLAB_DATA_DIR` to override them with absolute,
non-overlapping paths. The roots and their path components must be free of
symlinks.

| Directory | Owner-provisioned input |
| --- | --- |
| Config | Copy `docker/.env.example` to `.env`, mode 0600, and supply the tunnel ID and MCP token |
| Config | `tunnel-api-key`, `mcp-bearer`, and `Xilinx.lic`, mode 0600. The bearer file contains `Bearer <PANOLAB_MCP_TOKEN>` |
| Config | `codex-auth/` plus optional `github-git-auth/`, mode 0700 |
| Data | `agent-workspace/`, `repo-rpc/`, `Xilinx/`, `ise-work/`, mode 0700 |
| Data | Exactly one owner-provided ISE archive (`.tar`, `.tar.gz`, `.tgz`, or `.tar.bz2`). Existing `sync-backups/` and worker credentials remain under this root |

The installer requires these inputs to exist and preserves the existing
vendor installation. Keep credential contents, license details and archives
private. The owner laptop completed the external-storage migration. The
[cutover runbook](#owner-local-storage-recovery) preserves the original rollback
procedure and checkpoint-specific inputs.

## 3. Commands

From the repository checkout on the laptop:

```bash
bash ./panolab-install.sh --fresh-host-check  # read-only missing-prerequisite inventory, even before Docker
bash ./panolab-install.sh --status   # read-only status
bash ./panolab-install.sh --check    # local configuration preflight
bash ./panolab-install.sh            # build missing/stale-labeled images; start/reuse services
bash ./panolab-install.sh --upgrade-dev   # explicitly upgrade only the dev image/container
bash ./panolab-install.sh --enable-github-push  # opt-in GitHub direct push for repo-git only
```

The launcher verifies the user rootless Engine and private inputs,
merges the three Compose recipes, builds missing images **on the
laptop**, and brings up broker/repo/manager **without activating the
optional `ise-setup` profile**. It creates the bounded development
container if absent, checks available HDL tools, resource quotas
and Codex login, probes authenticated MCP (including anonymous denial),
then starts the outbound tunnel. The optional setup image can be built
but its container is not started during ordinary deployment.
This adjusted startup path has passed source/Compose tests, **not
an independent fresh-host installation**. Nothing in this recipe
touches the system/rootful Docker Engine, installs host packages,
changes unrelated containers or programs an FPGA.

GitHub publishes through the connected integration even without a laptop PAT.
To enable direct `repo_push` through the existing container, use the
[one-time fine-grained GitHub setup](#scoped-github-push), which puts
only a narrowly scoped token in the external owner configuration directory.
Never put that token in the ordinary development container or Git config.

A first-time Codex account may need an interactive owner-approved
login **inside the local development container** before installation
can complete. The dedicated private authentication bind preserves the login.
After a local tunnel start, verify remote `lab_status` and `repo_status`.

## 4. Operate and inspect

See [architecture](ARCHITECTURE.md) for current services and reboot evidence.
The optional setup container must already exist for normal `lab_lifecycle start`.

Inspect with authenticated PanoLab MCP `lab_status` / `repo_status`
or the read-only `--status` command.
The ordinary installer is **not yet** a clean-room reproducer of this
expanded configuration; see [the ISE milestone review](EVIDENCE.md#remote-ise-milestone). The user Docker socket is
`/run/user/$(id -u)/docker.sock`; never manage PanoLab through
the default system/rootful Docker Engine.

Use `dev_exec` for approved operations **inside** the already
running development container and its `/workspace` scratch.
The normal `dev_exec` operation runs inside the approved modern development
container and is not host Docker access. The explicitly owner-approved,
**temporary** `@maintenance` compatibility route is an exception: it
can perform broad operations on the **owner's rootless Docker Engine**
through the internal maintenance sidecar. Do not infer that rootless
Docker makes this control production-safe. The separate `@ise14` path
stages immutable RTL revisions and calls the installed licensed worker.
Neither grants authorization to JTAG, SPI, flash or hardware programming.
Avoid restarting the authenticated tunnel or worker for ordinary source edits.

The installer reuses existing services with `--no-recreate`. When the modern
image recipe changes, it rebuilds and smoke-tests the image tag and reports
that the running dev container still needs an explicit
[dev-only upgrade](#controlled-development-image-upgrade).
Before any service replacement,
review effects on the remote tunnel, host resources, private mounts,
licenses and persistent results. Do not globally prune Docker.
Reboot recovery was accepted for the **earlier six-service LM1 configuration**
on the owner's provisioned laptop, using `unless-stopped` for the
standalone developer container. Clean reboot acceptance remains open for the current setup-on-demand
deployment and the proposed six-service topology. The earlier
test does not prove unattended headless startup before login or a
fresh-host installation.

### Temporary management recovery

The already authorized maintenance helper offers `status` and `check` for
health, `reload-broker` for a Python-only restart, and `deploy-management`
for candidate image builds, tests, saved-image tags and rollback on a failed
authenticated canary. Run a broker or manager replacement detached through
the approved maintenance interface so loss of the remote session cannot
interrupt it. After reconnecting, inspect
`/workspace/maintenance/status.json` and `/workspace/maintenance/latest.log`
and verify authenticated normal service behavior. Keep the owner-local
recovery path available. See the
[retirement gate](ARCHITECTURE.md#approved-future-retirement-gate).

### Verify ISE result retrieval and license evidence

Build and test the worker and manager in the approved laptop rootless
Engine from the reviewed candidate checkout. These two stages run the
checksum-locked Go suites and compile the binaries.

```sh
docker buildx build --builder default --load --platform linux/amd64 --target mcp-builder \
  -t panolab-direct-ise14-worker:coherence-test -f docker/ise14/Dockerfile docker/ise14
docker buildx build --builder default --load --target build \
  -t panolab-direct-manager:coherence-test -f docker/control/Manager.Dockerfile docker
```

Build the worker `final` image with `--platform linux/amd64` for the existing guarded worker rebind,
with its exact image ID and restart policy. Before replacement, check the
live mounts, confirm the worker is idle and preserve the old worker
container and image for rollback. Preserve the results bind so historical
jobs remain available. Use the existing detached management deployment
for the broker and compiled manager, with its authenticated canary and
retained rollback images.

After rebind, check `ise_toolchain_info` and `@ise14 toolchain_info` for
`not_yet_validated` when the license is readable. Retrieve job
`1795652101955866441` through both normal result routes using
`Artifact: "design.twr"` and verify 71,042 bytes and SHA-256
`a238e8410ad444f76cb12b36c775a88dc64825e6649192c5a66cde554a273a88`.
Check metadata-only retrieval and rejection of an unsupported selector.
Stage and run an approved constrained fixture through the normal build
route. Confirm that both info adapters cite the new successful job, and
that the verified timing report includes its expected constraint target,
coverage and available setup and hold facts. Record source checks and live
licensed evidence separately.

### On-demand ISE setup controls

For the existing setup service, use authenticated `lab_lifecycle` with
`Container=panolab-direct-connect-setup-1` and `Operation=start`.
Inspect it using `@setup info`, `@setup status` or `@setup inspect`.
When finished, use the same lifecycle call with `Operation=stop`.
Vendor installation requires separate owner authorization, approved terms
and checksum validation.

### Controlled development image upgrade

1. Verify the clean canonical development checkout and reviewed revision.
   Use the guarded synchronization procedure in [development](#working-milestone-and-commit-discipline).
2. Run `bash ./panolab-install.sh --check`, then the explicitly authorized
   `bash ./panolab-install.sh --upgrade-dev`. The helper checks rootless
   preconditions, exact mounts and the recipe label, then smoke-tests the
   reviewed modern image offline before swapping the running dev.
3. Confirm the same dev name, workspace, private login, limits and read-only
   source with its Git mask. Verify live tool health and the relevant source
   checks. Keep the exact old container stopped for rollback. The helper
   attempts scoped rollback on failure. Cleanup needs a separate decision.

Keep the approved workspace, private Codex authentication bind and management
services available throughout the upgrade. The installer reuses the single
modern image tag and leaves the ISE worker separate.

Record the reviewed source SHA, applicable `SOURCE_UPDATE` result,
`LITEX_REQUIRED_TOOLS`, `DEV_UPGRADE_RESULT`, image ID, generated BIOS/HDL
artifacts and any `ROLLBACK_CONTAINER` line. For failures, report the exact
step and nonsecret error. Confirm live tool health, baseline simulation and
normal service availability via authenticated MCP before deciding separately
whether to remove the stopped rollback container. See [laptop evidence](EVIDENCE.md#unified-development-image).

### Disposable unattended ISE 14.7 acceptance

The **normal authenticated PanoLab interface**, not `@maintenance`,
owns the disposable acceptance test. The owner-approved
[ISE 14.7 acceptance policy](../docker/ise14/acceptance-policy.json)
pins the approved System Edition vendor archive by SHA-256 and
records the limited authorization to accept its known batch-installer
terms without an interactive prompt. New media or changed terms
require separate review.

The remote PanoLab connector's `dev_exec` supports these **fixed,
broker-intercepted argument arrays**, not general shell commands:

```text
["@ise-e2e", "preflight"]
["@ise-e2e", "start"]
["@ise-e2e", "status", "<12-hex-run-id>"]
["@ise-e2e", "result", "<12-hex-run-id>"]
```

`start` provisions fresh Docker **named volumes** and a separate
setup service, runs actual unattended installation and a separate
licensed worker build, validates six tool stages and their artifacts,
and deletes only that run's labeled Docker resources. Result metadata
and SHA-256 hashes are preserved in the broker's private management
volume. `@ise-e2e` never invokes the temporary maintenance route
and requires no laptop-side manual terminal steps after the approved
inputs are provisioned. The existing installation, license, normal
setup and persistent worker are never writable test inputs.

Acceptance requires the normal manager/broker path, the exact approved
archive and terms, an initially empty install volume, an unattended
successful native install, all six licensed stages, nonempty hashed
bitstream and timing report, and all eight run-scoped resources absent.
Verify `passed` and `disposed: true` and preservation of the persistent worker,
private inputs and stopped setup service. Maintenance may inspect the
framework. Execution or mid-run modification by maintenance invalidates
the run. Preflight currently requires the healthy persistent worker,
existing stopped setup for mount discovery, and known-good setup and
worker checkpoint images. Bounded results are private under
`/rpc/ise-e2e/` in the management RPC volume.

The successful end-to-end evidence and limitations are recorded in
[disposable ISE acceptance](EVIDENCE.md#disposable-ise-installation).
This capability proves a **fresh ISE vendor installation on the
already-provisioned laptop**, not an untouched-host installation of
Docker, a new entitlement, the tunnel, or Pano G2 hardware programming.

## 5. Source synchronization boundary

The canonical checkout is `~/Projects/repos/panolab-direct-main`,
but its **active branch** is `development`, tracking
`origin/development`. GitHub has exactly `main` and `development`.
At the LM1 freeze both were identical at `006b6ee`, with `main`
preserved as the accepted baseline. All engineering goes through
`development`, and promotion to `main` requires explicit owner
acceptance. Use guarded fast-forward sync only while the checkout
is clean and source history permits it; never reset or force-push
to hide divergence. Follow [development and publishing](#working-milestone-and-commit-discipline)
and [LM1 evidence](../specs/LAB_MILESTONE_1.md).

### Scoped GitHub push

Use the existing `repo-git` service for direct pushes. Keep GitHub write
credentials out of the modern development container.

The token goes in this ignored, owner-private file.

```text
${PANOLAB_CONFIG_DIR}/github-git-auth/github-push-token
```
The containing directory is mode **0700**, token file **0600**. The opt-in [Compose overlay](../docker/compose.git-push.yaml) mounts **only that directory** read-only at `/run/panolab-git-auth` in the existing `repo-git` service. Owner credentials and operational data are stored in the external roots. No GitHub credential goes in the runtime `.env`, `~/.gitconfig`, a remote URL, git command-line argument, Dockerfile, test log or chat.

The helper [`docker/control/github_askpass.py`](../docker/control/github_askpass.py) is enabled **only** for the gateway's allowlisted push. It reads the token directly from the read-only mount. The gateway continues to verify the expected GitHub origin and clean working tree, refuses force pushes, and permits direct pushes **only** to `refs/heads/development`. Remote branch protections and GitHub's normal permissions still apply.

#### Owner-local setup and renewal

1. In your browser, use [GitHub fine-grained personal access tokens](https://github.com/settings/personal-access-tokens/new). Choose owner **`sirchuckalot`**, access to **only `panolab-direct`**, repository permission **Contents: Read and write**, and a finite expiration. Metadata read permission is added automatically. Do not select broad organization/all-repository scopes.
2. From the local checkout, run the one command below as your ordinary laptop user **without sudo**. It will prompt for the token *without echoing it*, write it to the ignored private file, rebuild **only** the existing `repo-git` image and recreate **only** its service with the opt-in read-only mount. No ISE, dev-container or FPGA changes.
3. The script validates the mount scope and checks authentication through
   the credential helper with `git push --dry-run origin HEAD:refs/heads/development`.

```bash
cd "$HOME/Projects/repos/panolab-direct-main" && bash ./panolab-install.sh --enable-github-push
```

**Never paste a token into ChatGPT or send `github-push-token` file contents.** If it expires, revoke it in GitHub and use the same owner-local renewal workflow after inspecting the existing private file; the script deliberately refuses silently overwriting an existing credential.

The gateway permits explicit-file commits of at most 20 paths, checks parent
directories and recognizes the approved `research/` root. For larger atomic
changes, use reviewed local staging or the connected integration. Verify the
expected remote SHA after publication. Historical authentication results are
in [the evidence index](EVIDENCE.md#scoped-github-authentication).

## Development and verification

Follow [engineering session policy](../AGENTS.md) and the
[source and project standard](../specs/PANOLAB_SOURCE_AND_PROJECT_ARCHITECTURE.md).

### Choose the test venue

| Goal | Default execution |
| --- | --- |
| Bash/Python/Go lint and unit tests, HDL simulation and synthesis checks | Laptop development container or a dedicated local toolchain container |
| Dependencies, incompatible fixtures and repeatability experiments | Isolated, resource-limited local rootless container through approved broker controls |
| Rootless Docker, systemd/cgroups, mounts, authenticated MCP, network and Codex behavior | The **actual laptop** and running PanoLab services; never hosted CI as proxy |
| Licensed ISE, bitstream implementation and reproducibility | Separately approved persistent laptop-local ISE worker |
| JTAG/Etherbone, FPGA identity, configuration or flash | Owner-authorized physical laptop/board environment with recovery |
| Repository hygiene, deterministic clean-environment unit/lint/security checks | Local first; optional small, explicitly justified CI gate |

GitHub Actions is legitimate CI for fast reproducible checks,
review gates and platform portability tests. It is **not** a substitute
for the laptop's Docker/rootless setup, private credential environment,
licensed ISE or hardware. Before adding a workflow, state the concrete
question, clean-runner assumptions, trigger, timeout, cost budget and
what PASS can establish. No Actions workflows are required or shipped
in this baseline. Avoid hosted KVM and push/CI debugging loops.

### Working milestone and commit discipline

Follow the binding [development process](../AGENTS.md#mandatory-development-process)
and [repository ownership rules](../AGENTS.md#repository-ownership) when
planning, reviewing and publishing milestones.

Run experiments in the approved `/workspace` candidate.
Do not commit and push each trial.
Use `lab_status` and `repo_status` to inspect the laptop baseline and compare
the reported source revision with GitHub `development`. Use the connected
GitHub integration for publication, or follow the owner-local
[scoped GitHub push setup](#scoped-github-push) to enable the gateway route.
Before calling `repo_sync`, verify the published GitHub SHA and confirm that
the gateway supports the branch and both histories share ancestry. Apply
the remaining binding sync conditions and check `repo_status` afterward to
confirm the expected revision and a clean checkout.

### Local source checks

For a separately scoped audit of the frozen Rescue checkpoint, verify source bytes before compiling:

```sh
python3 shared/source_registry.py verify --project projects/rescue/project.toml
PANOLAB_LAB_MAC=02:00:00:00:00:01 bash projects/rescue/build.sh
bash projects/rescue/test.sh
```

Use the provisioned modern development toolchain; output is isolated
under `/workspace/panolab-projects/rescue-g2b/` unless explicitly redirected.
The historical G2 source checks and the platform suite are
separate test gates.

Use an approved laptop container with the project available:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m unittest discover -s tests -p 'test_litex_recipe.py' -v
python3 -m unittest discover -s tests -p 'test_upgrade_reconcile.py' -v
python3 -m unittest discover -s tests -p 'test_bios_overlay.py' -v
bash -n panolab-install.sh host/rootless-install.sh
python3 -m py_compile docker/control/broker.py docker/control/repo_gateway.py
```

The Go MCP manager and vendor MCP worker have in-tree Go tests,
normally executed inside locally built Go toolchain stages or
an approved local Go container. Keep the external
`tests/fixtures/ise_counter/` RTL/manifest and
`tests/ise_mcp_smoke_client.py` separate from the vendor worker.
The fixture is not a bitstream ready to program.

The [BIOS warning cleanup](EVIDENCE.md#toolchain-warning-cleanup) uses
six SHA-256-guarded, build-output-only overlays for the exact pinned
LiteX/Compiler-RT sources: no blanket warning suppression or rewrites
of the pristine upstream checkouts. A full G2 source build with zero
compiler/link warnings and RX/RW (not RWX) BIOS ELF LOAD segments
passed in the laptop development container. Docker image construction
uses owner-local Buildx on the existing rootless Engine, never a
second BuildKit service.

**Unified modern development image:** All open-source FPGA development tools share [one Dockerfile](../docker/modern/Dockerfile). Dedicated legacy vendor ISE remains separate. The [controlled dev-only upgrade](#controlled-development-image-upgrade) verifies source history and mounts and preserves a stopped rollback container before accepting a rebuilt image. Do not delete or recreate the running lab merely to add another HDL package.

See the [early LiteX BIOS bootstrap and source-build evidence](EVIDENCE.md#litex-bootstrap). The image
pins seven upstream checkouts and Python build versions; standard LiteX
BIOS builds do not require copying old Pano FPGA frameworks. A clean
workspace-install PASS and static recipe tests do **not** demonstrate
a new Docker image build, ISE bitstream, real FPGA boot, or TAP Ethernet
simulation (upstream TAP setup still needs a nonprivileged solution).

After the [external storage cutover](EVIDENCE.md#external-storage-cutover), the
standalone development container sees the entire canonical source checkout
at read-only `/repo`. Git administration is masked. Run source integrity and
simulation tests against `/repo`, and put build output and writable engineering
checkouts under `/workspace`.

```sh
python3 -B -m unittest discover -s /repo/tests -p 'test_panolab_csr_demo.py' -v
```

On the owner-host checkout, rerun the full source suite; tests
requiring Icarus/Yosys report `SKIP` if those tools are not installed
there, so a passing **container** simulation is still required.
For runtime changes, syntax and source tests are insufficient:
validate actual service and authentication behavior on the laptop.
Vendor/physical acceptance requires separate authorization and tests
per [architecture](ARCHITECTURE.md) and [security](ARCHITECTURE.md#security-and-trust-boundaries).


### Verify the pinned LiteX environment

In the modern dev container, load and verify the installed environment offline.

```sh
. /opt/panolab/litex/env.sh
python3 /opt/panolab/recipes/litex-bootstrap.py \
  --prefix /opt/panolab/litex \
  --lock /opt/panolab/recipes/litex-upstream.lock.json \
  --requirements /opt/panolab/recipes/litex-requirements.txt --verify-only
```

The image build fetches pinned public dependencies. Runtime verification uses
the installed pins. Advance corresponding source locks, the image marker and
verification evidence together when changing versions.

### Buildx and the guarded rollback cleanup

The [owner-local installer](../host/install-rootless-buildx.sh) pins Buildx
v0.36.1 and checks the release binary against its recorded SHA-256. It installs
under `~/.docker/cli-plugins` when needed and preserves a working plugin.
A missing binary requires network access. Image builds use
`docker buildx build --builder default --load` with the existing rootless
Engine's default Docker driver.

The historical, separately approved `bash ./panolab-install.sh --finalize-maintenance`
checks the rootless Engine, reviewed image and running dev identity, mounts,
tools and Buildx driver. Its only removal target is the exact stopped
`panolab-direct-dev-1-rollback-20261124T020818Z` with matching image and
workspace. The operation fails closed on mismatch and is idempotent if absent.
See the [original acceptance and scope](EVIDENCE.md#toolchain-warning-cleanup).

## Owner-local storage recovery

The [original cutover and rollback runbook](EVIDENCE.md#external-storage-cutover)
is revision-locked. Use an owner-local terminal because stopping ingress
disconnects the tunnel. Block submissions, drain all jobs, quiesce writers
and preserve the previous source, exact image and container IDs, restart and
mount metadata, private inputs and the metadata-only migration journal outside
the checkout. Recheck image IDs and ownership before any replacement action.

Use the original helper's read-only preflight and repeat its dry-run before
moves. Disable recorded restart policies before stopping the old containers,
tunnel first and maintenance last. Keep the old containers and tags available.
The storage helper checks overlapping live binds and journals same-filesystem
renames. Verify the read-only source and Git mask, writable mount scope,
authenticated and anonymous MCP behavior, Codex and resource limits, and
normal setup and ISE operations after replacement.

For rollback, stop and remove only identified replacements, preserve the
original RPC volume and network, and reverse the journal with the candidate
source while affected writers are stopped. Verify legacy paths, entry
identities and modes before starting any original container. Restore the
previous source, names, tags and restart policies by recorded ID, start only
the original running set with the tunnel last, and verify the original
authenticated interface. Keep services quiescent and retain the journal if
a rename cannot be reconciled.
