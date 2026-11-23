# Running and maintaining PanoLab

## Inspect the existing deployment

Inside ChatGPT, use the PanoLab MCP tools `lab_status` and
`repo_status`. The laptop's local read-only status command is:

```bash
bash ./panolab-install.sh --status
```

Expected operational components:
`panolab-direct-connect-tunnel-1`,
`panolab-direct-connect-manager-1`,
`panolab-direct-connect-docker-broker-1`,
`panolab-direct-connect-repo-git-1`,
`panolab-direct-connect-setup-1`,
`panolab-direct-dev-1` (six rootless containers).

The rootless Engine socket is
`/run/user/$(id -u)/docker.sock`. Do not use a default
system/rootful Docker daemon for PanoLab operations.

## Development and tests

Run targeted `dev_exec` commands inside the development container.
Use `/workspace` for transient work; approved source mounts are
available under `/repo`. For a risky dependency experiment, request
a separate locally isolated rootless container through an audited MCP
capability. Do not mount Docker's socket into a general-purpose agent
container or restart a persistent service as a test fixture.

## Update source: stop at a verified change

1. Inspect `repo_status`, the GitHub head and **branch ancestry**.
2. Define the intended behavior and local tests. Experiment in
   scratch or isolated laptop containers without test commits/pushes.
3. When relevant local tests and checks pass, review the full diff
   and label any still-unverified ISE/hardware gates PENDING.
4. **Create one coherent commit for the verified change**, publish
   through the connected GitHub integration with the expected parent,
   and check the resulting SHA. Don't publish per trial or CI retry.
5. Call `repo_sync` only for a clean, fast-forwardable checkout
   on the same history. The current old `development` checkout is
   unrelated to the clean `main` root history; don't overwrite it.

See [Git workflow](GIT_WORKFLOW.md) and [testing](TESTING.md).

## Service changes

The installer is not an unconditional repair or reset tool. It builds
missing images, validates private inputs and existing components,
then brings up rootless services with `--no-recreate`. It does not
install host Docker, delete anything, reset Codex auth, validate ISE
license or program hardware.

Before a restart or image replacement, review the exact change,
available disk, persistent mounts and effect on the authenticated
tunnel. No global Docker prune. The default system Docker daemon and
unrelated containers are outside PanoLab scope.

Full reboot recovery and automatic unattended re-entry are **not
established** by ordinary running-container status. Do not claim
such a pass without testing the real laptop.
