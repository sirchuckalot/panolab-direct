# Local-first testing

The **owner's laptop** is the authoritative environment for PanoLab
development and Docker acceptance. GitHub is used for version control,
not for rootless installation or heavyweight Docker test runs.

## Test levels

1. **Source:** syntax, static references, Go/Python unit tests and
   shell scripts inside the laptop development container or a
   dedicated local scratch container.
2. **Simulation:** HDL lint, Icarus/Verilator, synthesis checks and
   LiteX-generated test designs in local containers.
3. **Container integration:** rootless Engine security mode, systemd
   cgroups, CPU/RAM/PID quotas, image builds, mounts, RPC, bearer
   rejection and authenticated MCP from the actual laptop.
4. **Vendor build:** ISE installation, license availability, compiler
   stages, map/PAR/timing and artifact verification inside the
   persistent licensed worker. **Not validated merely by source tests**.
5. **Hardware:** owner-approved JTAG/volatile programming,
   trusted-LAN Etherbone reads and physical measurements. Never
   inferred from simulation.

Use the smallest relevant local test. Preserve authenticated services
and private data; scope disposable tests to dedicated containers.
Record command, image, exit code, hashes and proof level.

## Useful local source checks

```bash
# Run in an appropriate laptop container with the repository mounted.
python3 -m unittest discover -s tests -p 'test_*.py'
bash -n panolab-install.sh host/rootless-install.sh
```

Go tests are run in a **local** Go/toolchain container or during local
Docker image builds. The ISE MCP fixture in
`tests/fixtures/ise_counter/` is **not a bitstream to program**.

Hosted CI is optional only for a narrow, explicitly justified
source-control concern; it is not an alternative laptop runtime.
There are deliberately **no GitHub Actions workflows** in this
clean source snapshot.
