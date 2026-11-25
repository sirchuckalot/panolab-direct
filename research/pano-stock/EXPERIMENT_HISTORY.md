# Experiment history

1. Passive UDP listener returned no announcements. Host neighbor discovery and physical label established initial target. ICMP failed; lack of ping did not establish unreachable hardware.
2. Initial Python wrong destination port and ephemeral source port timed out. Correct fixed source 8320 and destination 8321 yielded actual board ID. Direct container unicast worked.
3. Read eight identity words; initial serial interpretation incorrect. Per-word byte reversal reconciled against photograph. Directed discovery found stock board in about 14.74 seconds on explicitly authorized /24; no known individual IP needed. Broadcast failed.
4. Four network words retrieved. Connectionless CSR request returned acknowledgement only, not data. Reliable stream with zero initial sequence worked, status read returned zero, own-session disconnect returned peer to zero.
5. Small boot/golden reads repeated, known Xilinx synchronization word observed. Factory prefix matched all seven known identity words. Two full factory-sector passes over 16 sessions matched.
6. Conservative reader measured about 2 KiB/s. Batching ordered read pairs and cumulative acknowledgements improved throughput. Automatic increment hypothesis rejected by repeated selected-word reads. Two independent contiguous 512 KiB acquisitions matched.
7. Sequential single-file full extent acquired freshly in order. At block 220 one batch returned no data; stopped without appending it, verified all checkpoint hashes and idle identity, resumed. No gaps, synthetic FF or substituted earlier samples. 512 block hashes and 47 prior-reference comparisons passed. Golden/main equal; upper 7 MiB erased.
8. Reference unit retained as stock. Future separate experimental unit must have its own identification, backup and recovery qualification before modifications.

Method: human sets objective, authorization, physical constraints; ChatGPT interprets evidence and selects bounded experiments; Codex contributes original components and offline research. Several Codex sessions timed out; framing and tests required independent correction. Preserve evidence before expanding scope. No worldwide-first claim.
