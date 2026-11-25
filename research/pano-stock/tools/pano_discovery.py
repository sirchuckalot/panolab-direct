# SPDX-License-Identifier: GPL-3.0-or-later
"""Read Pano G2 identity registers through an injected UDP datagram transport."""

from dataclasses import dataclass
from ipaddress import IPv4Address
import math
from time import monotonic
from typing import Callable, Iterable, Protocol


HOST_PORT = 8320
DEVICE_PORT = 8321
IDENTITY_ADDRESSES = (0, 1, 4, 5, 6, 7, 16, 17)
BOARD_MODELS = {0x08010000: "G2 B", 0x08010002: "G2 C"}


class DatagramTransport(Protocol):
    """Datagram interface using local UDP 8320 and numeric IPv4 peers."""

    def send(self, payload: bytes, peer: tuple[str, int]) -> None:
        """Send one datagram without blocking."""

    def receive(self, timeout: float) -> tuple[bytes, tuple[str, int]] | None:
        """Return one datagram and its sender, or None when the timeout expires."""


@dataclass(frozen=True)
class Identity:
    ip: str
    board_id: int
    model: str
    word_1: int
    serial: str
    mac: str


def decode_identity(ip: str, words: dict[int, int]) -> Identity:
    """Decode a complete set of identity words, preserving the raw word at address 1."""
    board_id = words[0]
    serial = b"".join(words[address].to_bytes(4, "little") for address in (4, 5, 6, 7))
    mac = (words[16] & 0xFFFF).to_bytes(2, "big") + words[17].to_bytes(4, "big")
    return Identity(
        ip, board_id, BOARD_MODELS[board_id], words[1],
        serial.rstrip(b"\x00").decode("ascii", errors="replace"), mac.hex(":"),
    )


def _read_request(address: int, transaction: int) -> bytes:
    if address not in IDENTITY_ADDRESSES:
        raise ValueError("address is outside the identity read allowlist")
    sequence = (transaction & 0xFFF) << 4
    return (
        b"\x01\x08" + sequence.to_bytes(2, "big") + bytes(4)
        + b"\x00\x06\x00" + address.to_bytes(3, "big")
        + transaction.to_bytes(2, "big")
    )


def _read_response(payload: bytes) -> tuple[int, int, int] | None:
    if (
        len(payload) != 20
        or payload[:2] != b"\x01\x08"
        or payload[8:11] != b"\x00\x0a\x20"
    ):
        return None
    return (
        int.from_bytes(payload[11:14], "big"),
        int.from_bytes(payload[14:16], "big"),
        int.from_bytes(payload[16:20], "big"),
    )


def _candidate_ips(candidates: Iterable[str]) -> list[str]:
    peers = {}
    for candidate in candidates:
        ip = IPv4Address(candidate)
        if ip.is_unspecified or ip.is_multicast or int(ip) == 0xFFFFFFFF:
            raise ValueError(f"candidate must be a unicast IPv4 address: {ip}")
        peers[str(ip)] = None
    return list(peers)


class DiscoveryCollector:
    """Collect complete G2 identities from owner-approved unicast IPv4 addresses.

    Use one collector per transport and call discover sequentially. Transaction
    IDs are never reused by a collector, including across discovery calls.
    """

    def __init__(
        self, transport: DatagramTransport, *, clock: Callable[[], float] = monotonic,
    ) -> None:
        self._transport = transport
        self._clock = clock
        self._next_transaction = 1

    def discover(self, candidates: Iterable[str], *, timeout: float = 1.0) -> list[Identity]:
        """Return complete identities in candidate order within one receive deadline."""
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        peers = _candidate_ips(candidates)
        if self._next_transaction + len(peers) * len(IDENTITY_ADDRESSES) > 0x10000:
            raise ValueError("insufficient unused transaction IDs for all candidates")

        deadline = self._clock() + timeout
        pending: dict[int, tuple[str, int]] = {}
        words: dict[str, dict[int, int]] = {}

        def send_read(ip: str, address: int) -> None:
            if self._clock() >= deadline:
                return
            transaction = self._next_transaction
            self._next_transaction += 1
            self._transport.send(_read_request(address, transaction), (ip, DEVICE_PORT))
            pending[transaction] = (ip, address)

        for ip in peers:
            send_read(ip, 0)

        while pending:
            remaining = deadline - self._clock()
            if remaining <= 0:
                break
            datagram = self._transport.receive(remaining)
            if datagram is None or self._clock() >= deadline:
                break
            payload, (ip, port) = datagram
            if port != DEVICE_PORT:
                continue
            response = _read_response(payload)
            if response is None:
                continue
            address, transaction, value = response
            if pending.get(transaction) != (ip, address):
                continue
            del pending[transaction]
            if address == 0:
                if value not in BOARD_MODELS:
                    continue
                words[ip] = {0: value}
                for identity_address in IDENTITY_ADDRESSES[1:]:
                    send_read(ip, identity_address)
            else:
                words[ip][address] = value

        return [
            decode_identity(ip, words[ip])
            for ip in peers
            if len(words.get(ip, {})) == len(IDENTITY_ADDRESSES)
        ]
