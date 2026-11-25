# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline throughput estimates and decoding of endpoint-zero read responses."""

import math
import struct
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_RTT_SECONDS = 0.001
VALUE_BYTES = 4
READ_RESPONSE_OPCODE = 0x50
_HEADER = struct.Struct(">H")
_BODY = struct.Struct(">B3sHI")


@dataclass(frozen=True)
class ReadResponse:
    address: int
    transaction_id: int
    value: int


def stop_and_wait_throughput(rtt_seconds: float = DEFAULT_RTT_SECONDS) -> float:
    """Return payload bytes/s for one four-byte value per two RTTs."""
    return VALUE_BYTES / (2 * _validated_rtt(rtt_seconds))


def batched_throughput(
    pairs_per_batch: int, rtt_seconds: float = DEFAULT_RTT_SECONDS
) -> float:
    """Return payload bytes/s assuming one RTT per batch of ordered pairs.

    Each pair yields one four-byte value. The model accounts only for RTT.
    """
    if type(pairs_per_batch) is not int or pairs_per_batch < 1:
        raise ValueError("pairs_per_batch must be a positive integer")
    return VALUE_BYTES * pairs_per_batch / _validated_rtt(rtt_seconds)


def _validated_rtt(rtt_seconds: float) -> float:
    if not math.isfinite(rtt_seconds) or rtt_seconds <= 0:
        raise ValueError("rtt_seconds must be finite and positive")
    return rtt_seconds


def parse_read_responses(
    data: bytes, expected_transactions: Mapping[int, int]
) -> list[ReadResponse]:
    """Decode complete frames in wire order, matching transaction IDs to addresses.

    Each expected transaction must appear exactly once. Raise ValueError for
    malformed frames or a mismatch with the expected transactions.
    """
    remaining = dict(expected_transactions)
    responses = []
    offset = 0
    while offset < len(data):
        frame_offset = offset
        if len(data) - offset < _HEADER.size:
            raise ValueError(f"truncated header at offset {frame_offset}")
        (header,) = _HEADER.unpack_from(data, offset)
        endpoint, length = header >> 11, header & 0x7FF
        if endpoint != 0:
            raise ValueError(f"unexpected endpoint {endpoint} at offset {frame_offset}")
        if length != _BODY.size:
            raise ValueError(f"invalid body length {length} at offset {frame_offset}")

        offset += _HEADER.size
        if len(data) - offset < length:
            raise ValueError(f"truncated body at offset {frame_offset}")
        opcode, address_bytes, transaction_id, value = _BODY.unpack_from(data, offset)
        if opcode != READ_RESPONSE_OPCODE:
            raise ValueError(f"unexpected opcode 0x{opcode:02x} at offset {frame_offset}")
        if transaction_id not in expected_transactions:
            raise ValueError(f"unexpected transaction ID 0x{transaction_id:04x}")
        if transaction_id not in remaining:
            raise ValueError(f"duplicate transaction ID 0x{transaction_id:04x}")

        address = int.from_bytes(address_bytes, "big")
        if address != remaining.pop(transaction_id):
            raise ValueError(f"address mismatch for transaction ID 0x{transaction_id:04x}")
        responses.append(ReadResponse(address, transaction_id, value))
        offset += length

    if remaining:
        missing = ", ".join(f"0x{tid:04x}" for tid in remaining)
        raise ValueError(f"missing transaction IDs: {missing}")
    return responses
