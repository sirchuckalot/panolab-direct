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
bash -n panolab-install.sh host/rootless-install.sh
python3 -m py_compile docker/control/broker.py docker/control/repo_gateway.py
```

The Go MCP manager and vendor MCP worker have in-tree Go tests,
normally executed inside locally built Go toolchain stages or
an approved local Go container. Keep the external
`tests/fixtures/ise_counter/` RTL/manifest and
`tests/ise_mcp_smoke_client.py` separate from the vendor worker.
The fixture is not a bitstream ready to program.

For runtime changes, syntax and source tests are insufficient:
validate the actual affected service behavior and authentication
on the laptop. For vendor/physical acceptance, use the separate
authorization gates described in [architecture](ARCHITECTURE.md)
and [security](SECURITY.md).

## Current source-control caveat

The live laptop `development` checkout and clean GitHub `main`
have unrelated ancestry. They **cannot** be made equal with a
routine fast-forward. Until separately migrated and verified,
leave the running gateway and its checkout intact. This is a
current operational constraint, not a reason to force-reset
Git history or use CI as a workaround.

[Install and operation](GETTING_STARTED.md) ·
[Architecture](ARCHITECTURE.md) ·
[Agent working rules](../AGENTS.md)
