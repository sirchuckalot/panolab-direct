# Iterations 1–15

The detailed original records below preserve the actual sequence rather than retroactively claiming all components were present in a final image.

| Iteration | Main outcome | Evidence class |
|---:|---|---|
| 1 | Baseline pinned source generation, BIOS/Verilog and ISE staging; baseline ISE lacked a system clock constraint | Source/vendor attempt |
| [2](iteration-02.txt) | Correct period constraints expose setup failures; boot policy and standalone ICAP experiments | Vendor failed timing; model tests |
| [3](iteration-03.txt) | Reset CDC and buffered SPI Wishbone timing correction; UART-only diagnostic BIOS | Vendor timing pass on earlier candidate; native/build |
| [4](iteration-04.txt) | Storage bounds, two-copy journal, read-only JEDEC probe | Native/RV32 and source build |
| [5](iteration-05.txt) | Streaming hash, NOR transaction and trial lifecycle | Synthetic NOR and native tests |
| [6](iteration-06.txt) | Canonical manifest, persistent manifest model and fixed-address read-only diagnostic | Vendor timing pass; native |
| [7](iteration-07.txt) | Integrated mock update controller, normalized identity record and diagnostic client | Native/mock; no real network |
| [8](iteration-08.txt) | Actual VexRiscv BIOS execution in behavioral GMII simulation; SPI NOR component | Full-system sim and native |
| [9](iteration-09.txt) | Protected persistent read-only probe and synthetic identity/journal inspection | CPU simulation and ISE staging |
| [10](iteration-10.txt) | Latest diagnostic ISE timing pass; isolated ICAP interlock and streaming session | Vendor diagnostic; RTL/native models |
| [11](iteration-11.txt) | Managed transaction owner, provisional wire parser and product-size synthetic upload | Native mock SPI |
| [12](iteration-12.txt) | Synthetic RAM-only BIOS network upload; physical mutation path not implemented | CPU/GMII simulation |
| [13](iteration-13.txt) | Bounded peer-owned session, replay and lockout | Native and CPU/GMII simulation |
| [14](iteration-14.txt) | Host injected-transport client, expiry and abrupt-process-reset experiments | Native/CPU simulation |
| [15](iteration-15.txt) | Abstract durable operation ledger, fresh-process reconciliation and host read-only decision model | Native and RV32 components; earlier GMII evidence revalidated |

Iteration 15 did not generate a new FPGA bitstream or integrate its ledger into the CPU/GMII appliance. The 28 regression groups passed historically and were rerun for checkpoint publication. Previous failures, Codex timeouts, corrected tests, assumptions and pending gates remain recorded in the original iteration reports. The human, ChatGPT and Codex method follows the [stock research workflow](../../../../research/pano-stock/AGENTIC_WORKFLOW.md): narrowly scoped hypotheses, implementation, test, independent review and evidence retention.
