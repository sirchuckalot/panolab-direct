"""Host-only boot policy and journal fault-injection tests."""

import unittest
from dataclasses import replace

from rescue_boot_model import (
    ERASED, MAX_SEQUENCE, SECTOR_BYTES, BootConfig, Cut, Image, Journal, Launch,
    Mode, PowerLoss, Record, Rescue, ReturnEvidence, Trial, UnsafeState,
)


A = "a" * 64
B = "b" * 64
HIGH = (True, True, True)
LOW = (False, False, False)
INITIAL = Record(0, confirmed="A", confirmed_digest=A)


def verified(digest):
    return Image(digest, True, True, True, True, True, True)


def controller(journal=None, **options):
    options.setdefault("identity_valid", True)
    return Rescue(journal or Journal.provisioned(INITIAL),
                  {"A": verified(A), "B": verified(B)}, **options)


def sector(record):
    return record.encode().ljust(SECTOR_BYTES, b"\xff")


class BootTests(unittest.TestCase):
    def test_bounded_autoboot_without_network(self):
        for timeout in (1, 5000, 10000):
            with self.subTest(timeout=timeout):
                rescue = controller(config=BootConfig(timeout_ms=timeout))
                self.assertEqual(rescue.start(HIGH), Mode.WINDOW)
                self.assertIsNone(rescue.poll(timeout - 1))
                self.assertEqual(rescue.poll(timeout), Launch("A", A))
                self.assertIsNone(rescue.poll(timeout + 1))
        for value in (0, 10001, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                BootConfig(timeout_ms=value)

    def test_active_low_hold_latches_and_mixed_samples_do_not_hold(self):
        rescue = controller()
        for levels in (HIGH, (False, False, True), (True, False, False)):
            self.assertEqual(rescue.start(levels), Mode.WINDOW)
        self.assertEqual(rescue.start(LOW), Mode.HELD)
        self.assertIsNone(rescue.poll(100000))
        rescue.images["A"] = Image(A)
        with self.assertRaises(UnsafeState):
            rescue.boot_confirmed()
        self.assertEqual(rescue.mode, Mode.HELD)
        rescue.images["A"] = verified(A)
        self.assertEqual(rescue.boot_confirmed(), Launch("A", A))

    def test_optional_hold_during_window(self):
        rescue = controller()
        rescue.start(HIGH)
        rescue.poll(4999)
        rescue.hold()
        self.assertIsNone(rescue.poll(5000))
        self.assertEqual(rescue.mode, Mode.HELD)

    def test_bad_samples_fail_closed(self):
        for levels in (None, (), (False, False), (0, 0, 0), HIGH + HIGH):
            with self.subTest(levels=levels):
                rescue = controller()
                self.assertEqual(rescue.start(levels), Mode.RECOVERY)
                self.assertIsNone(rescue.poll(5000))
                with self.assertRaises(UnsafeState):
                    rescue.prepare("B")

    def test_no_usable_confirmed_image_and_reverify_at_deadline(self):
        rescue = controller(Journal.provisioned(Record(0)))
        self.assertEqual(rescue.start(HIGH), Mode.IDLE)
        self.assertIsNone(rescue.poll(5000))
        for image in (None, Image(A), verified(B)):
            with self.subTest(image=image):
                rescue = controller()
                rescue.images["A"] = image
                self.assertEqual(rescue.start(HIGH), Mode.IDLE)
                rescue.images["A"] = verified(A)
                self.assertEqual(rescue.start(HIGH), Mode.WINDOW)
                rescue.images["A"] = image
                self.assertIsNone(rescue.poll(5000))
                self.assertEqual(rescue.mode, Mode.IDLE)

    def test_invalid_identity_blocks_start_and_rechecked_before_launch(self):
        for value in (False, None, 1):
            rescue = controller(identity_valid=value)
            self.assertEqual(rescue.start(LOW), Mode.RECOVERY)
            self.assertIsNone(rescue.poll(5000))
            with self.assertRaises(UnsafeState):
                rescue.prepare("B")
        rescue = controller()
        rescue.start(HIGH)
        rescue.identity_valid = False
        self.assertIsNone(rescue.poll(5000))
        self.assertEqual(rescue.mode, Mode.RECOVERY)

    def test_recovery_only_blocks_confirmed_boot_even_if_held(self):
        rescue = controller(Journal.provisioned(replace(INITIAL, state="recovery_only")))
        self.assertEqual(rescue.start(HIGH), Mode.RECOVERY)
        self.assertIsNone(rescue.poll(5000))
        rescue.start(LOW)
        with self.assertRaises(UnsafeState):
            rescue.boot_confirmed()


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.rescue = controller()
        self.rescue.start(LOW)

    def launch(self):
        self.rescue.prepare("B")
        self.assertEqual(self.rescue.journal.read().state, "trial_pending")
        launch = self.rescue.boot_trial()
        self.assertEqual(launch, Launch("B", B, Trial(2, B)))
        self.assertEqual(self.rescue.journal.read().attempts, 0)
        return launch.trial

    def test_verification_gates_before_prepare_and_launch(self):
        fields = ("target_ok", "length_format_ok", "signing_policy_ok",
                  "readback_ok", "metadata_ok", "bootable")
        for field in fields:
            with self.subTest(field=field):
                self.rescue.images["B"] = replace(verified(B), **{field: False})
                with self.assertRaises(UnsafeState):
                    self.rescue.prepare("B")
                self.assertEqual(self.rescue.journal.read(), INITIAL)
        for slot in ("A", None, "RESCUE", "IDENTITY"):
            with self.subTest(slot=slot), self.assertRaises(UnsafeState):
                self.rescue.prepare(slot)
        self.rescue.images["B"] = verified(B)
        self.rescue.prepare("B")
        self.rescue.images["B"] = verified(A)
        with self.assertRaises(UnsafeState):
            self.rescue.boot_trial()
        self.assertEqual(self.rescue.journal.read().attempts, 1)

    def test_pending_survives_reset_without_automatic_trial_launch(self):
        self.rescue.prepare("B")
        restarted = controller(Journal(self.rescue.journal.snapshot()))
        self.assertEqual(restarted.start(HIGH), Mode.WINDOW)
        self.assertEqual(restarted.poll(5000), Launch("A", A))
        self.assertEqual(restarted.journal.read().state, "trial_pending")

    def test_unconfirmed_reset_and_bad_return_evidence_roll_back(self):
        trial = self.launch()
        snapshot = self.rescue.journal.snapshot()
        for evidence in (None, ReturnEvidence(trial), ReturnEvidence(Trial(1, B), True),
                         ReturnEvidence(Trial(2, A), True), ReturnEvidence(trial, 1)):
            with self.subTest(evidence=evidence):
                restarted = controller(Journal(snapshot))
                self.assertEqual(restarted.start(HIGH, returned=evidence), Mode.WINDOW)
                record = restarted.journal.read()
                self.assertEqual((record.state, record.confirmed, record.pending, record.attempts),
                                 ("rollback_required", "A", None, 0))
                with self.assertRaises(UnsafeState):
                    restarted.boot_trial()
                with self.assertRaises(UnsafeState):
                    restarted.confirm(trial, approved=True)
                self.assertEqual(restarted.poll(5000), Launch("A", A))
        restarted = controller(Journal(snapshot))
        self.assertEqual(restarted.start(LOW), Mode.HELD)
        self.assertIsNone(restarted.poll(5000))

    def test_return_and_confirmation_require_live_exact_evidence(self):
        trial = self.launch()
        with self.assertRaises(UnsafeState):
            self.rescue.confirm(trial, approved=True)
        self.assertEqual(self.rescue.start(HIGH, returned=ReturnEvidence(trial, True)),
                         Mode.RETURNED)
        self.assertIsNone(self.rescue.poll(5000))
        for invalid, approved in ((Trial(1, B), True), (Trial(2, A), True),
                                  (Trial(2.0, B), True), (trial, False), (trial, 1)):
            with self.subTest(trial=invalid, approved=approved), self.assertRaises(UnsafeState):
                self.rescue.confirm(invalid, approved=approved)
        self.rescue.images["B"] = Image(B)
        with self.assertRaises(UnsafeState):
            self.rescue.confirm(trial, approved=True)
        self.rescue.images["B"] = verified(B)
        self.rescue.confirm(trial, approved=True)
        restarted = controller(Journal(self.rescue.journal.snapshot()))
        self.assertEqual(restarted.start(HIGH, returned=ReturnEvidence(trial, True)), Mode.WINDOW)
        with self.assertRaises(UnsafeState):
            restarted.prepare("A")
        self.assertEqual(restarted.poll(5000), Launch("B", B))
        self.assertEqual(restarted.start(LOW), Mode.HELD)
        restarted.rollback()
        self.assertEqual(restarted.boot_confirmed(), Launch("A", A))

    def test_failed_first_trial_stays_in_rescue(self):
        rescue = controller(Journal.provisioned(Record(0)))
        rescue.start(HIGH)
        rescue.prepare("B")
        rescue.boot_trial()
        self.assertEqual(rescue.start(HIGH), Mode.IDLE)
        self.assertIsNone(rescue.poll(5000))

    def test_old_return_cannot_confirm_a_later_trial_of_same_image(self):
        old = self.launch()
        self.rescue.start(LOW)
        self.rescue.prepare("B")
        new = self.rescue.boot_trial().trial
        self.assertEqual(new.manifest_digest, old.manifest_digest)
        self.assertNotEqual(new.trial_id, old.trial_id)
        self.assertEqual(self.rescue.start(LOW, returned=ReturnEvidence(old, True)), Mode.HELD)
        with self.assertRaises(UnsafeState):
            self.rescue.confirm(new, approved=True)
        self.assertEqual(self.rescue.journal.read().confirmed, "A")

    def test_explicit_release_allows_preparing_prior_slot(self):
        trial = self.launch()
        self.rescue.start(LOW, returned=ReturnEvidence(trial, True))
        self.rescue.confirm(trial, approved=True)
        self.rescue.prepare("A", release_previous=True)
        record = self.rescue.journal.read()
        self.assertEqual((record.confirmed, record.pending, record.previous), ("B", "A", None))

    def test_explicit_cancel_pending(self):
        self.rescue.prepare("B")
        self.rescue.rollback()
        with self.assertRaises(UnsafeState):
            self.rescue.boot_trial()
        self.assertEqual(self.rescue.boot_confirmed(), Launch("A", A))


class JournalTests(unittest.TestCase):
    def test_rejects_empty_corrupt_and_ambiguous_journals(self):
        original = sector(INITIAL)
        for offset in (0, 4, 6, 10, len(INITIAL.encode()) - 3,
                       len(INITIAL.encode()) - 1, SECTOR_BYTES - 1):
            damaged = bytearray(original)
            damaged[offset] ^= 1
            with self.subTest(offset=offset):
                self.assertIsNone(Record.decode(damaged))
                self.assertEqual(Journal((damaged, original)).read(), INITIAL)
                self.assertEqual(controller(Journal((damaged, ERASED))).start(HIGH), Mode.RECOVERY)
        conflict = replace(INITIAL, confirmed="B", confirmed_digest=B)
        gap = replace(INITIAL, sequence=2)
        for pair in ((ERASED, ERASED), (original, sector(conflict)), (original, original),
                     (original, sector(gap))):
            with self.subTest(pair=pair), self.assertRaises(UnsafeState):
                journal = Journal(pair)
                self.assertEqual(controller(journal).start(HIGH), Mode.RECOVERY)
                journal.read()

    def test_stale_invalid_and_wrapping_commits_preserve_sectors(self):
        journal = Journal.provisioned(INITIAL)
        snapshot = journal.snapshot()
        for expected, proposed in ((replace(INITIAL, reason="other"), replace(INITIAL, sequence=1)),
                                   (INITIAL, replace(INITIAL, sequence=2)),
                                   (INITIAL, replace(INITIAL, sequence=1, attempts=1))):
            with self.assertRaises(UnsafeState):
                journal.commit(expected, proposed)
            self.assertEqual(journal.snapshot(), snapshot)
        last = replace(INITIAL, sequence=MAX_SEQUENCE)
        journal = Journal((sector(last), ERASED))
        with self.assertRaises(UnsafeState):
            journal.commit(last, replace(last, sequence=MAX_SEQUENCE + 1))
        self.assertEqual(journal.read(), last)

    def test_all_byte_cuts_through_trial_lifecycle(self):
        pending = replace(INITIAL, sequence=1, state="trial_pending", pending="B",
                          pending_digest=B, attempts=1, reason="trial_prepared")
        running = replace(pending, sequence=2, state="trial_running", attempts=0,
                          reason="trial_started")
        confirmed = Record(3, confirmed="B", confirmed_digest=B, previous="A",
                           previous_digest=A, reason="trial_confirmed")
        rolled_back = replace(INITIAL, sequence=3, state="rollback_required",
                              reason="unconfirmed_trial")
        trial = Trial(2, B)
        transitions = (
            (Journal.provisioned(INITIAL).snapshot(), INITIAL, pending,
             lambda rescue, cut: rescue.prepare("B", cut=cut)),
            ((sector(INITIAL), sector(pending)), pending, running,
             lambda rescue, cut: rescue.boot_trial(cut=cut)),
            ((sector(running), sector(pending)), running, confirmed,
             lambda rescue, cut: rescue.confirm(trial, approved=True, cut=cut)),
            ((sector(running), sector(pending)), running, rolled_back,
             lambda rescue, cut: rescue.start(HIGH, cut=cut)),
        )
        for snapshot, before, after, operation in transitions:
            for phase, length in (("erase", SECTOR_BYTES), ("program", len(after.encode()) - 1),
                                  ("commit", 1)):
                for n in range(length + 1):
                    with self.subTest(transition=after.reason, phase=phase, n=n):
                        rescue = controller(Journal(snapshot))
                        evidence = ReturnEvidence(trial, True) if before == running else None
                        rescue.start(LOW, returned=evidence)
                        with self.assertRaises(PowerLoss):
                            operation(rescue, Cut(phase, n))
                        self.assertEqual(rescue.mode, Mode.OFF)
                        preserved = before.sequence % 2
                        self.assertEqual(rescue.journal.snapshot()[preserved], snapshot[preserved])
                        restarted = controller(Journal(rescue.journal.snapshot()))
                        committed = phase == "commit" and n == 1
                        self.assertEqual(restarted.journal.read(), after if committed else before)
                        self.assertEqual(restarted.start(HIGH), Mode.WINDOW)
                        expected_slot = "B" if after == confirmed and committed else "A"
                        expected_digest = B if expected_slot == "B" else A
                        self.assertEqual(restarted.poll(5000), Launch(expected_slot, expected_digest))

    def test_repeated_interruptions_retry_using_persisted_sectors(self):
        snapshot = Journal.provisioned(INITIAL).snapshot()
        for cut in (Cut("program", 20), Cut("erase", 3), Cut("commit", 0)):
            rescue = controller(Journal(snapshot))
            rescue.start(LOW)
            with self.assertRaises(PowerLoss):
                rescue.prepare("B", cut=cut)
            self.assertEqual(rescue.journal.read(), INITIAL)
            snapshot = rescue.journal.snapshot()
        rescue = controller(Journal(snapshot))
        rescue.start(LOW)
        rescue.prepare("B")
        self.assertEqual(rescue.boot_trial().trial, Trial(2, B))


if __name__ == "__main__":
    unittest.main()
