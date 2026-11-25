# Observed stock G2 register map

| Configuration address | Interpretation |
|---|---|
| 0x00 | Board ID, measured Rev B 0x08010000 |
| 0x01 | Firmware ID, measured 0x08010014 |
| 0x04–0x07 | Serial: reverse bytes within each 32-bit word |
| 0x10–0x11 | MAC: low 16 bits of first word, then second word |
| 0x12 | IPv4 |
| 0x13 | Mask |
| 0x16 | Gateway |
| 0x18 | Current controller peer, zero when idle |

Rev C board ID 0x08010002 is reference/synthetic-discovery evidence only. All 12 configuration words above were retrieved on the tested unit. Physical label matched revision, serial and MAC. Actual unique values intentionally omitted.

Ordinary CSR 0xff returned zero in the idle reference session; bit semantics not established. CSR space is distinct from configuration space. The historical flash read mechanism uses a volatile address selector and separate data retrieval register, not a flash program operation. Only the qualified read behavior was tested; unknown register operations may have side effects. No arbitrary register sweep or general hardware write interface is included. [Protocol](PROTOCOL.md).
