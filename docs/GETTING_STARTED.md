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
Codex and the [pinned LiteX/VexRiscv Rescue stack](RESCUE_ENVIRONMENT_RECIPE.md):
LiteX BIOS, LiteX-Boards, LiteEth, LiteSPI, Migen, SPI/PHY support,
RISC-V GCC/binutils, Meson/Ninja and simulation C libraries.
Licensed ISE remains separately approved. **Host Docker Buildx** is a
Docker CLI extension (not another Docker image or development service).
For the owner-laptop version-pinned, no-sudo bootstrap and exact
old-development-rollback cleanup, see the
[toolchain cleanup procedure](DEV_TOOLCHAIN_WARNING_CLEANUP.md).
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
Read [the actual test and remaining gates](FRESH_HOST_ACCEPTANCE.md).

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
[cutover runbook](EXTERNAL_STORAGE_CUTOVER.md) preserves the original rollback
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
See the [LiteX environment recipe](RESCUE_ENVIRONMENT_RECIPE.md). Before any service replacement,
review effects on the remote tunnel, host resources, private mounts,
licenses and persistent results. Do not globally prune Docker.
Reboot recovery was accepted for the **earlier six-service LM1 configuration**
on the owner's provisioned laptop, using `unless-stopped` for the
standalone developer container. Clean reboot acceptance remains open for the current setup-on-demand
deployment and the proposed six-service topology. The earlier
test does not prove unattended headless startup before login or a
fresh-host installation.

### On-demand ISE setup controls

For the existing setup service, use authenticated `lab_lifecycle` with
`Container=panolab-direct-connect-setup-1` and `Operation=start`.
Inspect it using `@setup info`, `@setup status` or `@setup inspect`.
When finished, use the same lifecycle call with `Operation=stop`.
Vendor installation requires separate owner authorization, approved terms
and checksum validation.

### Controlled development image upgrade

1. Verify the clean canonical development checkout and reviewed revision.
   Use the guarded synchronization procedure in [development](DEVELOPMENT.md).
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

The successful end-to-end evidence and limitations are recorded in
[disposable ISE acceptance](ISE14_DISPOSABLE_INSTALL_ACCEPTANCE.md).
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
to hide divergence. Follow [development and publishing](DEVELOPMENT.md)
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

[Architecture](ARCHITECTURE.md) · [Security](SECURITY.md)
