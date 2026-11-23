# Docker recipes

The live setup is defined by three Compose files:

```text
docker/compose.setup.yaml
docker/compose.manage.yaml
host/compose.rootless-laptop.yaml
```

The audited `host/rootless-install.sh` supplies project name,
private media mount and necessary path variables; it targets only
the user's `/run/user/<uid>/docker.sock`.

- `modern/Dockerfile`: Ubuntu Yosys/Icarus/Verilator and pinned
  Codex binaries. The development container is created with bounded
  resources and narrow project mounts.
- `control/Broker.Dockerfile`, `control/broker.py`: allowlisted
  lifecycle broker for the **rootless user** Docker Engine.
- `control/Repo.Dockerfile`, `control/repo_gateway.py`: constrained
  Git operations against one approved checkout; secrets masked.
- `control/Manager.Dockerfile`, `control/mcp/`: Go MCP manager and
  proxy to setup/broker/repository services.
- `ise14/`: CentOS 6.10 ISE setup image, pinned build inputs and
  embedded persistent five-tool MCP worker. Licensed installation
  requires private owner media and separate approval.

No CI, nested Docker daemon, host package installation, broad
Docker socket mount into developer containers, or FPGA programming.
See `../docs/SETUP.md` and `../docs/SECURITY.md`.
