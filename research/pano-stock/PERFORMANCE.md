# Physical readback benchmarks

| Words per request batch | KiB/s, 256 B factory sample |
|---:|---:|
| Original stop-and-wait | 2.09 |
| 1 | 4.24 |
| 2 | 5.00 |
| 4 | 10.04 |
| 8 | 20.52 |
| 16 | 24.88 |
| 32 | 35.28 |
| 64 | 39.36 |

Original 32 KiB: 16.33 seconds, 24,583 TX and 16,388 RX including session operations. 72-word batch: 32 KiB in 0.695 seconds, 46.05 KiB/s, exact comparison against golden reference. Cumulative ACK intervals 2–72 passed; host TX reduced to 228 per 32 KiB with interval 72 (transfer only), little effect on throughput. Chosen interval 16. Independent 512 KiB runs including setup, writes and checks: 41.31 and 41.52 KiB/s, equal. Full acquisition successful operations 366.732 s (6m 7s), not total wall clock. Approximately 21x sustained improvement. One response packet per word remains a likely bottleneck, not proof of ultimate hardware limit. No native block response or additional pipelining qualified. The throughput model is illustrative and does not predict measured hardware ceilings.
