# Stock Pano G2 research — PL-STOCK-001

November 24, 2026 (Pacific). One physical stock G2 Rev B tested. This is an experimental source suite, not a production updater or a restoration qualification.

The laboratory acquired the entire documented 16 MiB stock SPI extent over Ethernet without JTAG, enclosure opening, executing the old updater, or issuing flash program/erase commands. 512 blocks, 47 prior-reference comparisons, 366.732 seconds of successful read operations. One timeout was recovered at a verified checkpoint. Full second pass and direct JEDEC identification remain outstanding.

## Navigation
- [Protocol](PROTOCOL.md) — observed transport behavior and bounds.
- [Register map](REGISTER_MAP.md) — measured configuration words.
- [Flash layout](FLASH_LAYOUT.md) — physical observation versus published geometry.
- [Experiment history](EXPERIMENT_HISTORY.md) — staged discoveries and failed assumptions.
- [Performance](PERFORMANCE.md) — actual benchmark results.
- [Sources and licensing](SOURCES.md) — provenance and publication boundary.
- [Agentic workflow](AGENTIC_WORKFLOW.md) — human, ChatGPT and Codex roles, experiment cycle and lessons.
- [Tools and testing](TOOLS.md) — source entry points, qualification and private outputs.

## Operating policy
Reference unit: retain stock firmware and investigate only nonpersistent behavior. Experimental units: identify and preserve their own backups independently; require a separate recovery plan and explicit authorization before any programming. No cross-device factory data substitution. Use an isolated owner-controlled lab, no Internet exposure, no concurrent controller. Neither device identity nor TNP is cryptographic authentication.

Only newly authored Python and sanitized research are included. Raw ROM, captured frames with actual device identifiers, private logs, historical executable/disassembly and unique hashes remain outside Git. The generalized candidate has offline tests; the original device-specific implementation was physically tested. Do not equate the two qualification levels.
