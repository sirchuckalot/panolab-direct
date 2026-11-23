# System architecture

PanoLab Direct uses the owner's **local rootless Docker Engine** and
private MCP tools. No VM, nested Docker or hosted CI system is necessary.

```text
ChatGPT
  │ outbound authenticated Secure MCP Tunnel
  ▼
tunnel ──> manager (Go, private MCP endpoint)
             │ private RPC
             ├─> docker-broker (Python) ──> owner's rootless Docker socket
             ├─> repo-git (Python) ──> one approved source checkout
             └─> setup (CentOS 6.10, ISE provisioning/inspection)

development (Ubuntu 24.04): Yosys, Icarus, Verilator, Codex,
                            selected source directories + private workspace

future persistent licensed ISE worker:
  vendor toolchain + embedded MCP service in ONE runtime container
```

The deployed Compose definition is the merge of
`docker/compose.setup.yaml`, `docker/compose.manage.yaml` and
`host/compose.rootless-laptop.yaml`. The modern development container
is managed by the restricted broker, not the Compose project.

User namespaces map rootless container UID 0 to the laptop owner's
ordinary UID. This is not host root and is **not** complete isolation
from the owner's files. Apply narrow mounts, capabilities and Docker
socket restrictions; see [security](SECURITY.md).

The engineering target is a Pano Logic G2 Rev B Spartan-6 system with
LiteEth MAC/PHY, Etherbone Wishbone master, CSR identity/status and
bounded read/write register. Follow the owner-selected architecture
in `specs/PANOLAB_DIRECT_v1_0.txt`. LiteScope and coherent frame
snapshots are later design increments. All hardware programming
requires explicit approval.

The hosted GitHub integration publishes reviewed source, and the
restricted repository gateway only fast-forwards a clean local checkout.
GitHub CI is **not** the laptop test environment.
