# Canonical vendor toolchain MCP contract

Every FPGA vendor build appliance is a **persistent runtime container**
with a specified operating system, libraries, separately installed
licensed vendor toolchain and embedded MCP server. Pin exact versions
before reproducible build claims. The MCP server runs **inside the same
container as the build tools**; no MCP sidecar, SSH build controller,
agent shell or second runtime worker is required. A multi-stage
image build used to compile the MCP binary is allowed.

All vendor workers implement exactly these **five mandatory MCP tools**:

| Tool | Purpose |
| --- | --- |
| `toolchain_info` | Report identity, installed version, part support, license availability, image/runtime identity and capabilities |
| `build_start` | Validate a declared project/target/profile and enqueue one bounded build; return a stable job ID |
| `build_status` | Return state, progress/stages and bounded metadata for a job |
| `build_result` | Return bounded logs, stage outcomes, artifact names/sizes/hashes and optionally artifact byte chunks |
| `build_cancel` | Request cancellation of a specific running job; preserve recorded evidence |

The standard build profile `ise14-implementation` executes real
ISE stages as supported by the installed owner-supplied license and
project (for example XST, NGDBuild, MAP, PAR, TRACE, BitGen). A source
fixture is a **client-selected project**, not an embedded appliance
smoke test. External clients decide pass/fail and retrieve verifiable
artifacts. The worker remains running across multiple jobs and
retains bounded durable job status; do not recreate it per build.

A successful `build_result` does **not** authorize programming any
FPGA. Programming/JTAG/SPI/flash operations require an independent
explicit approval boundary. Vendor MAC/HOSTID requirements must be
verified and licensing respected.

Workers must reject unchecked shell commands, traversal paths,
unsafe mounts, cross-project artifact access and unrelated host
operations. Keep build inputs read-only, outputs and logs isolated
by job, and published diagnostics free of private tokens or license
material. Do not add vendor-specific agent-facing tools without
owner-approved interface revision.

The ISE 14.7 worker implementation lives in `docker/ise14/mcp/`.
**Vendor implementation acceptance for generic unconstrained XC6SLX150
smoke designs was achieved on 2026-11-24:** two real runs completed all
six stages and generated independently hashed nonempty bitstreams
([evidence](EVIDENCE.md#licensed-ise-bring-up)).
The node-locked license is satisfied by an explicitly managed,
Docker-**internal** virtual Ethernet identity without publishing the
private host ID. This does **not** qualify any board-specific pinout,
timing budget or physical programming.

The manager exposes additional *adapter* operations
`ise_project_stage`, `ise_worker_diagnostics` and named wrappers for
the five worker operations. Those adapter operations are not extra
mandatory tools inside the vendor worker. During development, the
owner-approved `@ise14` compatibility route and temporary maintenance
bridge provide remote control; see
[temporary maintenance controls](ARCHITECTURE.md#temporary-maintenance-and-retirement).

**Disposable installation acceptance is a separate normal control-plane
workflow, not a sixth mandatory vendor worker tool.** The authenticated
`@ise-e2e` broker adapter creates a disposable setup and vendor worker
using the same canonical MCP contracts, verifies the exact
[owner-authorized vendor archive policy](../docker/ise14/acceptance-policy.json),
performs the genuine six-stage pipeline, and then removes only its
labeled test resources. Successful artifacts are recorded by SHA-256
in the normal broker's private state volume. The existing persistent
worker is not modified or reinstalled. See
[the full acceptance contract](ISE14_DISPOSABLE_INSTALL_ACCEPTANCE.md).
This framework must remain independent of the temporary
`trusted-maintenance` route.

[Architecture and acceptance gates](ARCHITECTURE.md) · [Security](SECURITY.md)
