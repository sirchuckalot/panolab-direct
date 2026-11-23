# Agent integration

The agent uses the restricted PanoLab MCP manager to reach the local
rootless Docker development environment. Use LiteX RemoteClient and
approved LiteX APIs for the G2 board; never invent a competing raw
programming transport.

The baseline is source editing, simulation, builds and read-only
observations. FPGA write/configuration capabilities require an
owner-approved hardware broker with bounded operations, exact target
verification and rollback/recovery.

The initial hardware target is a **CPU-less** Etherbone-accessible
CSR identity and test register. All hardware access remains pending
until the licensed toolchain and physical board are verified.
