# Rev B SPI flash layout

Reference M25P128: 16 MiB, 64 sectors of 256 KiB, pages 256 bytes. Actual acquisition covers 0x000000–0xFFFFFF inclusive, 4,194,304 words; JEDEC ID not directly measured, aliasing not independently excluded. Rev C differs and its factory offset is inconsistent in community references; no Rev C backup qualification.

| Region | Inclusive addresses | Allocated bytes | Observed non-FF bytes |
|---|---|---:|---:|
| Boot | 0x000000–0x03FFFF | 262144 | 53 |
| Golden | 0x040000–0x47FFFF | 4456448 | 4143602 |
| Main | 0x480000–0x8BFFFF | 4456448 | 4143602 |
| Factory | 0x8C0000–0x8FFFFF | 262144 | 228 |
| Upper | 0x900000–0xFFFFFF | 7340032 | 0 |

Complete golden and main allocations were identical on the tested board. Upper 28 sectors entirely FF, physically read rather than synthesized. Non-FF count is not bitstream length. Sync at boot +4 and both image starts +16. Factory sector has 29 eight-byte records, seven type 0x1000 and 22 type 0x4000, last non-FF offset 231; seven known identity words matched live registers and label. Two complete independent factory-sector acquisitions matched. Full-chip image acquired once sequentially and checked against all block hashes and earlier anchors. Restore not demonstrated. Private raw image and identity sectors must not be committed.
