# PanoLab Direct

A rootless Docker FPGA development laboratory on the owner's Linux laptop.
It provides a modern HDL and firmware environment, authenticated MCP, scoped
source and container operations, and an isolated licensed Xilinx ISE 14.7
worker. The reference target is the Pano Logic G2 Rev B (XC6SLX150-2-FGG484).

| Start here | Purpose |
| --- | --- |
| [Architecture](docs/ARCHITECTURE.md) | Operating baseline, ownership, trust boundaries and open qualifications |
| [Installation and operations](docs/GETTING_STARTED.md) | Installation, development, verification, maintenance and recovery |
| [Engineering sessions](AGENTS.md) | Binding instructions for owner, ChatGPT and Codex |
| [Managed launcher](agent/README.md) | Job admission, result records and activation |
| [Vendor API](docs/TOOLCHAIN_MCP_CONTRACT.md) | Five persistent worker operations and control-plane adapters |
| [Evidence index](docs/EVIDENCE.md) | Dated tests, migration records and qualification limits |
| [Source and project standard](specs/PANOLAB_SOURCE_AND_PROJECT_ARCHITECTURE.md) | Ownership, dependencies, source closure, provenance and licensing |

The [system specification](specs/PANOLAB_DIRECT_v1_0.txt) covers the CPU-less
application. The [boot and recovery standard](specs/PANOLAB_RESCUE_V1.md)
covers the separate recovery personality. Anchor is the active product.
[Rescue](projects/rescue/README.md) is frozen engineering history, and
[stock-device research](research/pano-stock/README.md) records a separate
physical investigation. The [license index](LICENSES/README.md) identifies
PanoLab and upstream terms.
