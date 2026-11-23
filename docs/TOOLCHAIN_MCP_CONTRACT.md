# Canonical vendor toolchain MCP contract

Every FPGA vendor build appliance is a **persistent runtime container**
with its own pinned operating system, libraries, licensed vendor
toolchain and MCP server. The MCP server runs **inside the same
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

The ISE 14.7 implementation is source code in `docker/ise14/mcp/`.
It must be separately proven with licensed media and real toolchain
execution on the laptop before claiming vendor-build acceptance.
