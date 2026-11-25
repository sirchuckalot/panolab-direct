#!/usr/bin/env python3
"""Rescue v1.1 host model. All persistent state is simulated in memory."""

import json
import re
import struct
import zlib
from dataclasses import asdict, dataclass, replace
from enum import Enum


class UnsafeState(ValueError):
    pass


class PowerLoss(RuntimeError):
    pass


class Mode(Enum):
    OFF = "off"
    RECOVERY = "recovery_only"
    HELD = "held"
    IDLE = "idle"
    WINDOW = "autoboot_window"
    RETURNED = "trial_returned"
    APPLICATION = "application"


def digest_ok(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def binding_ok(slot, digest):
    return (slot is None and digest is None) or (slot in ("A", "B") and digest_ok(digest))


MAX_SEQUENCE = (1 << 64) - 1
MAGIC = b"RSJ1"
VERSION = 1
HEADER = struct.Struct(">4sBH")
CRC = struct.Struct(">I")
# Synthetic format capacity, in bytes per independent simulated erase unit.
SECTOR_BYTES = 512
ERASED = b"\xff" * SECTOR_BYTES


@dataclass(frozen=True)
class Record:
    sequence: int
    state: str = "stable"
    confirmed: str | None = None
    confirmed_digest: str | None = None
    pending: str | None = None
    pending_digest: str | None = None
    attempts: int = 0
    previous: str | None = None
    previous_digest: str | None = None
    reason: str = "provisioned"

    def validate(self):
        if type(self.sequence) is not int or not 0 <= self.sequence <= MAX_SEQUENCE:
            raise UnsafeState("invalid sequence")
        for slot, digest in ((self.confirmed, self.confirmed_digest),
                             (self.pending, self.pending_digest),
                             (self.previous, self.previous_digest)):
            if not binding_ok(slot, digest):
                raise UnsafeState("invalid slot binding")
        slots = [slot for slot in (self.confirmed, self.pending, self.previous)
                 if slot is not None]
        if len(set(slots)) != len(slots) or (self.previous and not self.confirmed):
            raise UnsafeState("inconsistent slots")
        if self.state not in ("stable", "trial_pending", "trial_running",
                              "rollback_required", "recovery_only"):
            raise UnsafeState("unknown state")
        trial = self.state in ("trial_pending", "trial_running")
        if trial != (self.pending is not None):
            raise UnsafeState("inconsistent pending slot")
        expected_attempts = int(self.state == "trial_pending")
        if type(self.attempts) is not int or self.attempts != expected_attempts:
            raise UnsafeState("invalid attempt count")
        if not isinstance(self.reason, str) or re.fullmatch(r"[a-z_]{1,32}", self.reason) is None:
            raise UnsafeState("invalid boot reason")

    def encode(self):
        self.validate()
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode("ascii")
        body = HEADER.pack(MAGIC, VERSION, len(payload)) + payload
        frame = body + CRC.pack(zlib.crc32(body)) + b"\x00"
        if len(frame) > SECTOR_BYTES:
            raise UnsafeState("record exceeds simulated sector")
        return frame

    @classmethod
    def decode(cls, sector):
        try:
            magic, version, length = HEADER.unpack_from(sector)
            if magic != MAGIC or version != VERSION:
                return None
            end = HEADER.size + length
            record = cls(**json.loads(sector[HEADER.size:end].decode("ascii")))
            frame = record.encode()
            # Canonical bytes also validate CRC, commit byte and erased padding.
            if sector == frame.ljust(SECTOR_BYTES, b"\xff"):
                return record
        except (ValueError, TypeError, struct.error, RecursionError):
            pass
        return None


@dataclass(frozen=True)
class Cut:
    """Power loss after exactly n byte operations in one write phase."""

    phase: str
    n: int


class Journal:
    def __init__(self, sectors=None):
        if sectors is None:
            sectors = (ERASED, ERASED)
        if len(sectors) != 2 or any(len(sector) != SECTOR_BYTES for sector in sectors):
            raise ValueError("expected two independent simulated erase sectors")
        self._sectors = [bytearray(sector) for sector in sectors]

    @classmethod
    def provisioned(cls, initial):
        if initial.sequence != 0:
            raise ValueError("initial sequence must be zero")
        return cls((initial.encode().ljust(SECTOR_BYTES, b"\xff"), ERASED))

    def snapshot(self):
        return tuple(bytes(sector) for sector in self._sectors)

    def _head(self):
        valid = [(i, record) for i, sector in enumerate(self.snapshot())
                 if (record := Record.decode(sector)) is not None]
        if not valid:
            raise UnsafeState("no valid journal record")
        valid.sort(key=lambda entry: entry[1].sequence)
        if len(valid) == 2 and valid[1][1].sequence - valid[0][1].sequence != 1:
            raise UnsafeState("ambiguous journal history")
        return valid[-1]

    def read(self):
        return self._head()[1]

    def commit(self, expected, new, cut=None):
        active, current = self._head()
        if current != expected or new.sequence != current.sequence + 1:
            raise UnsafeState("stale or nonconsecutive journal write")
        frame = new.encode()
        lengths = {"erase": SECTOR_BYTES, "program": len(frame) - 1, "commit": 1}
        if cut is not None and (cut.phase not in lengths or type(cut.n) is not int
                                or not 0 <= cut.n <= lengths[cut.phase]):
            raise ValueError("invalid cut point")
        target = self._sectors[1 - active]
        for phase, data in (("erase", ERASED), ("program", frame[:-1]),
                            ("commit", frame[-1:])):
            offset = len(frame) - 1 if phase == "commit" else 0
            if phase == "commit" and bytes(target) != frame[:-1].ljust(SECTOR_BYTES, b"\xff"):
                raise UnsafeState("journal body readback failed")
            count = cut.n if cut is not None and cut.phase == phase else len(data)
            for i in range(count):
                if phase == "erase":
                    target[i] = 0xff
                else:
                    target[offset + i] &= data[i]
            if cut is not None and cut.phase == phase:
                raise PowerLoss(f"{phase} interrupted after {count} bytes")
        if self._head() != (1 - active, new):
            raise UnsafeState("journal readback failed")


@dataclass(frozen=True)
class Image:
    """Results supplied by a trusted image verifier for the current slot bytes."""

    manifest_digest: str
    target_ok: bool = False
    length_format_ok: bool = False
    signing_policy_ok: bool = False
    readback_ok: bool = False
    metadata_ok: bool = False
    bootable: bool = False

    def verified(self):
        checks = (self.target_ok, self.length_format_ok, self.signing_policy_ok,
                  self.readback_ok, self.metadata_ok, self.bootable)
        return digest_ok(self.manifest_digest) and all(check is True for check in checks)


@dataclass(frozen=True)
class Trial:
    trial_id: int
    manifest_digest: str

    def matches(self, expected):
        return (type(self.trial_id) is int and self.trial_id == expected.trial_id
                and self.manifest_digest == expected.manifest_digest)


@dataclass(frozen=True)
class ReturnEvidence:
    trial: Trial
    health_observed: bool = False


@dataclass(frozen=True)
class Launch:
    slot: str
    manifest_digest: str
    trial: Trial | None = None


@dataclass(frozen=True)
class BootConfig:
    timeout_ms: int = 5000
    button_samples: int = 3

    def __post_init__(self):
        if type(self.timeout_ms) is not int or not 1 <= self.timeout_ms <= 10000:
            raise ValueError("timeout must be 1 through 10000 model milliseconds")
        if type(self.button_samples) is not int or not 2 <= self.button_samples <= 64:
            raise ValueError("startup window must have 2 through 64 samples")


class Rescue:
    def __init__(self, journal, images, *, identity_valid=False, config=BootConfig()):
        self.journal = journal
        self.images = images
        self.identity_valid = identity_valid
        self.config = config
        self.mode = Mode.OFF
        self._returned = None
        self._elapsed = 0
        self._sampled = False

    def _record(self):
        if self.identity_valid is not True:
            self.mode = Mode.RECOVERY
            raise UnsafeState("invalid identity")
        try:
            return self.journal.read()
        except UnsafeState:
            self.mode = Mode.RECOVERY
            raise

    def _write(self, record, cut, **changes):
        new = replace(record, sequence=record.sequence + 1, **changes)
        try:
            self.journal.commit(record, new, cut)
        except PowerLoss:
            self.mode = Mode.OFF
            self._returned = None
            raise
        except UnsafeState:
            self.mode = Mode.RECOVERY
            raise
        return new

    def _verified(self, slot, digest):
        image = self.images.get(slot)
        return isinstance(image, Image) and image.verified() and image.manifest_digest == digest

    @staticmethod
    def _trial(record):
        return Trial(record.sequence, record.pending_digest)

    def _discard_trial(self, record, cut, reason):
        return self._write(record, cut, state="rollback_required", pending=None,
                           pending_digest=None, attempts=0, reason=reason)

    def start(self, button_levels, *, returned=None, cut=None):
        """Enter Rescue first. Supply one active-low level per startup sample."""
        self.mode = Mode.RECOVERY
        self._returned = None
        self._elapsed = 0
        self._sampled = False
        try:
            record = self._record()
        except UnsafeState:
            return self.mode
        try:
            levels = tuple(button_levels)
        except TypeError:
            return self.mode
        if len(levels) != self.config.button_samples or any(type(level) is not bool for level in levels):
            return self.mode
        self._sampled = True
        held = not any(levels)
        if record.state == "trial_running":
            trial = self._trial(record)
            if (isinstance(returned, ReturnEvidence) and returned.health_observed is True
                    and isinstance(returned.trial, Trial) and returned.trial.matches(trial)
                    and self._verified(record.pending, record.pending_digest)):
                self._returned = trial
                self.mode = Mode.RETURNED
                return self.mode
            try:
                record = self._discard_trial(record, cut, "unconfirmed_trial")
            except UnsafeState:
                return self.mode
        if held:
            self.mode = Mode.HELD
        elif record.state == "recovery_only":
            self.mode = Mode.RECOVERY
        elif self._verified(record.confirmed, record.confirmed_digest):
            self.mode = Mode.WINDOW
        else:
            self.mode = Mode.IDLE
        return self.mode

    def _require_mode(self, *modes):
        if not self._sampled or self.mode not in modes:
            raise UnsafeState("operation unavailable in current mode")

    def poll(self, elapsed_ms):
        """Advance time since startup sampling completed. No link state is needed."""
        if type(elapsed_ms) is not int or elapsed_ms < self._elapsed:
            raise ValueError("elapsed milliseconds must be monotonic")
        self._elapsed = elapsed_ms
        if self.mode == Mode.WINDOW and elapsed_ms >= self.config.timeout_ms:
            try:
                return self.boot_confirmed()
            except UnsafeState:
                return None
        return None

    def hold(self):
        self._require_mode(Mode.WINDOW)
        self.mode = Mode.HELD

    def boot_confirmed(self):
        self._require_mode(Mode.IDLE, Mode.HELD, Mode.WINDOW)
        record = self._record()
        if record.state in ("recovery_only", "trial_running"):
            raise UnsafeState("journal disallows confirmed boot")
        if not self._verified(record.confirmed, record.confirmed_digest):
            if self.mode == Mode.WINDOW:
                self.mode = Mode.IDLE
            raise UnsafeState("confirmed image is unavailable or unverified")
        self.mode = Mode.APPLICATION
        return Launch(record.confirmed, record.confirmed_digest)

    def prepare(self, slot, *, release_previous=False, cut=None):
        """Journal an already staged, verified inactive slot before trial launch."""
        self._require_mode(Mode.IDLE, Mode.HELD, Mode.WINDOW, Mode.RECOVERY)
        record = self._record()
        if record.state in ("trial_pending", "trial_running") or slot not in ("A", "B") or slot == record.confirmed:
            raise UnsafeState("slot cannot be prepared")
        if slot == record.previous and release_previous is not True:
            raise UnsafeState("slot retained for rollback")
        image = self.images.get(slot)
        if not isinstance(image, Image) or not image.verified():
            raise UnsafeState("candidate is unverified")
        self._write(record, cut, state="trial_pending", pending=slot,
                    pending_digest=image.manifest_digest, attempts=1, previous=None,
                    previous_digest=None, reason="trial_prepared")

    def boot_trial(self, *, cut=None):
        self._require_mode(Mode.IDLE, Mode.HELD, Mode.WINDOW, Mode.RECOVERY)
        record = self._record()
        if record.state != "trial_pending" or not self._verified(record.pending, record.pending_digest):
            raise UnsafeState("no verified pending trial")
        running = self._write(record, cut, state="trial_running", attempts=0,
                              reason="trial_started")
        self.mode = Mode.APPLICATION
        return Launch(running.pending, running.pending_digest, self._trial(running))

    def confirm(self, trial, *, approved=False, cut=None):
        self._require_mode(Mode.RETURNED)
        record = self._record()
        if (record.state != "trial_running" or self._returned != self._trial(record)
                or not isinstance(trial, Trial) or not trial.matches(self._returned)
                or approved is not True or not self._verified(record.pending, record.pending_digest)):
            raise UnsafeState("confirmation rejected")
        self._write(record, cut, state="stable", confirmed=record.pending,
                    confirmed_digest=record.pending_digest, pending=None, pending_digest=None,
                    previous=record.confirmed, previous_digest=record.confirmed_digest,
                    reason="trial_confirmed")
        self._returned = None
        self.mode = Mode.HELD

    def rollback(self, *, cut=None):
        """Cancel a pending/returned trial or select the retained verified image."""
        self._require_mode(Mode.IDLE, Mode.HELD, Mode.WINDOW, Mode.RETURNED)
        record = self._record()
        if record.state in ("trial_pending", "trial_running"):
            self._discard_trial(record, cut, "explicit_rollback")
        elif record.state != "recovery_only" and self._verified(record.previous, record.previous_digest):
            self._write(record, cut, state="stable", confirmed=record.previous,
                        confirmed_digest=record.previous_digest, previous=record.confirmed,
                        previous_digest=record.confirmed_digest, reason="explicit_rollback")
        else:
            raise UnsafeState("no eligible rollback")
        self._returned = None
        self.mode = Mode.HELD


if __name__ == "__main__":
    digest = "a" * 64
    journal = Journal.provisioned(Record(0, confirmed="A", confirmed_digest=digest))
    verified = Image(digest, True, True, True, True, True, True)
    rescue = Rescue(journal, {"A": verified}, identity_valid=True)
    print("Startup", rescue.start((True, True, True)).value)
    print("Before deadline", rescue.poll(4999))
    print("At deadline", rescue.poll(5000))
