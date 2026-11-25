# Proposed Trusted-LAN manifest wire format

A version 1 manifest is one definite-length CBOR map occupying 1 through 2,048
bytes. Use the shortest CBOR representation for unsigned integers and all
lengths. Sort map keys by the lexicographic order of their encoded bytes. For
the text keys below, this is length order followed by ASCII order. Every listed
key occurs exactly once, with the sole exception of the optional
`build_id` key. Duplicate keys, extra keys (including signing fields), and
bytes following the map are rejected.

The top-level map has exactly 11 entries. The tables list keys in wire order.

| Key | CBOR value and constraints |
| --- | --- |
| `image_id` | Printable ASCII text |
| `image_role` | Text `application` |
| `image_length` | Unsigned integer from 1 through 2⁶⁴ − 1, giving the unpadded raw image length in bytes |
| `image_sha256` | 32-byte byte string containing the SHA-256 digest of the unpadded raw image |
| `config_format` | Text `xilinx-spartan6-spi` |
| `image_version` | Printable ASCII text |
| `build_provenance` | Map with three required entries and one optional entry |
| `manifest_version` | Unsigned integer `1` |
| `required_features` | Empty array or one-element array containing the text `icap-return-v1` |
| `supported_targets` | One-element array containing the target map below |
| `required_rescue_api` | Two-element array of unsigned integers `[1, minor]`, where `minor` is the minimum supported minor version, from 0 through 2³² − 1 |

The target map has exactly four entries.

| Key | CBOR text value |
| --- | --- |
| `board_id` | `pano-g2` |
| `fpga_part` | `xc6slx150-2-fgg484` |
| `bsp_profile` | `pano-g2-revb/1` |
| `board_revision` | `b` |

The provenance map contains the following entries.

| Key | CBOR value and constraints |
| --- | --- |
| `build_id` | Optional printable ASCII text |
| `toolchain` | Printable ASCII text |
| `git_commit` | Exactly 40 lowercase hexadecimal ASCII characters |
| `dependency_pins` | Array of 0 through 12 printable ASCII text entries |

Each printable ASCII text value is 1 through 96 bytes, all in the range
`0x20` through `0x7e`. On success the parser returns image metadata and the
SHA-256 digest of the complete encoded manifest. The format provides
Trusted-LAN integrity metadata. The caller applies image size and compatibility
policy and verifies the raw image separately. A parse failure leaves the output
object unchanged.
