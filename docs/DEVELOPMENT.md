# Develop, test and publish

**Use the laptop's existing rootless Docker laboratory for engineering.**
GitHub is the source/review system; publication happens only at a
verified logical stopping point, not per experiment.

## Choose the test venue

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

## Working milestone and commit discipline

1. Check source status and GitHub refs, identify the active checkout
   and define the smallest complete engineering objective and tests.
2. Experiment in `/workspace`, a disposable local checkout or a
   reviewed isolated container. **Do not commit and push each trial.**
3. Rerun appropriate laptop-local checks until the actual feature
   works. Check implementation and credentials/mount boundaries.
4. Review the final diff and record exactly what passed: command,
   execution site, test result and any separate PENDING gate. Source
   tests are not proof of a licensed or physical FPGA build.
5. Publish **one coherent, reviewed commit** for the verified change
   using the connected GitHub integration and an expected-parent,
   non-force update. Draft/unverified work requires explicit approval.
6. Verify the new GitHub SHA. Only use PanoLab `repo_sync` when the
   checkout is clean, the gateway supports the branch, and the
   histories share ancestry. Never wipe local work or silently
   reconcile unrelated histories.

New, independently verified milestones earn new commits. Failed local
experiments, runner permutations and transient logs are *not*
published milestones.

## Local source checks

Use an approved laptop container with the project available:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m unittest discover -s tests -p 'test_litex_recipe.py' -v
python3 -m unittest discover -s tests -p 'test_upgrade_reconcile.py' -v
bash -n panolab-install.sh host/rootless-install.sh
python3 -m py_compile docker/control/broker.py docker/control/repo_gateway.py
```

The Go MCP manager and vendor MCP worker have in-tree Go tests,
normally executed inside locally built Go toolchain stages or
an approved local Go container. Keep the external
`tests/fixtures/ise_counter/` RTL/manifest and
`tests/ise_mcp_smoke_client.py` separate from the vendor worker.
The fixture is not a bitstream ready to program.

**Unified modern development image:** All open-source FPGA development tools share [one Dockerfile](../docker/modern/Dockerfile). Dedicated legacy vendor ISE remains separate. The [controlled dev-only upgrade](UNIFIED_DEV_IMAGE_UPGRADE.md) verifies source history and mounts and preserves a stopped rollback container before accepting a rebuilt image. Do not delete or recreate the running lab merely to add another HDL package.

Rootless LiteX BIOS provisioning and source builds are documented in
[RESCUE_ENVIRONMENT_RECIPE.md](RESCUE_ENVIRONMENT_RECIPE.md). The image
pins seven upstream checkouts and Python build versions; standard LiteX
BIOS builds do not require copying old Pano FPGA frameworks. A clean
workspace-install PASS and static recipe tests do **not** demonstrate
a new Docker image build, ISE bitstream, real FPGA boot, or TAP Ethernet
simulation (upstream TAP setup still needs a nonprivileged solution).

The default standalone development container mounts **selected**
repository subtrees only, not the checkout root. Consequently the
full `test_snapshot_integrity.py` suite needs to run from the host
ordinary-user checkout or an approved full-source test environment;
it will fail with missing paths if run inside the deliberately
limited `/repo` container mount. That is **not** a reason to enlarge
its source mounts or weaken private isolation.

The LM2 simulation-only CSR fixture *can* be run inside the restricted
development container, since `gateware` and `tests` are already
mounted:

```sh
python3 -m unittest discover -s /repo/tests -p 'test_panolab_csr_demo.py' -v
```

On the owner-host checkout, rerun the full source suite; tests
requiring Icarus/Yosys report `SKIP` if those tools are not installed
there, so a passing **container** simulation is still required.
For runtime changes, syntax and source tests are insufficient:
validate actual service and authentication behavior on the laptop.
Vendor/physical acceptance requires separate authorization and tests
per [architecture](ARCHITECTURE.md) and [security](SECURITY.md).

## Current source-control baseline

GitHub retains exactly two branches: `main` and `development`.
They were identical at the accepted LM1 freeze commit `006b6ee`.
The laptop's canonical directory `~/Projects/repos/panolab-direct-main`
has **`development`** checked out, tracking `origin/development`.
Do all experiments, edits and reviewed development commits on
`development`; **never** publish directly to `main` without the
owner's explicit acceptance. The histories share ancestry and can
use guarded fast-forward synchronization while they do not diverge.
No stale branch or unrelated-history reset is part of routine work.

See the [LM1 acceptance report](../specs/LAB_MILESTONE_1.md) for
the software-lab baseline, lessons and next acceptance gates.

[Install and operation](GETTING_STARTED.md) ·
[Architecture](ARCHITECTURE.md) ·
[Agent working rules](../AGENTS.md)
