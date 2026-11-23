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

## Proper role of CI

CI is a standard practice for **automated, repeatable checks** on a
reviewed change: formatting, lint, fast unit tests, source security
checks, reproducible builds and narrowly chosen PR gates. It can be
useful when a fresh, controlled environment adds evidence. This is
different from using hosted runners as an improvised replacement for
the user's laptop.

Choose CI only after stating the concrete question, why the laptop
container is not the right venue, input/environment assumptions,
bounded runtime/cost, trigger and the meaning of PASS. Do not run
GitHub Docker/KVM iterations to debug rootless installation, laptop
user namespaces, systemd delegation, private credentials, ISE or
hardware. There are **no GitHub Actions workflows** in this snapshot;
adding one requires a justified, small, deterministic contract.

## Working stopping point

Before publication, define the expected behavior and the checks
that will prove it. Iterate in scratch or local isolated containers;
do not push failed experiments. When a change is ready:

- Relevant local syntax/unit/simulation checks pass; relevant laptop
  integration passes if the change affects runtime.
- Review the complete diff for scope, generated files and secrets.
- Report exact venue/commands and PASS; label unavailable licensed or
  FPGA/hardware gates PENDING, never implied passed.
- Make one coherent commit for that verified logical result, and push
  once. Separate verified features deserve separate commits, but
  trial-and-error and CI reruns do not.
- Verify the remote SHA; fast-forward the local checkout only when
  clean and on the same history.

Keep long-running experimentation local; no CI loop is a substitute
for the actual laptop acceptance environment.
