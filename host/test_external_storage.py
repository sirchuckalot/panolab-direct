"""Synthetic tests for the owner-local filesystem transaction."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "migration", Path(__file__).with_name("migrate-external-storage.py"))
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


class Migration(unittest.TestCase):
    def setUp(self):
        initial = tempfile.TemporaryDirectory()
        self.addCleanup(initial.cleanup)
        root = Path(initial.name)
        self.repo, self.config, self.data = (root / item for item in ("source", "config", "data"))
        self.legacy = self.repo / "docker/private"
        for path in (self.legacy, self.config, self.data):
            path.mkdir(parents=True, mode=0o700)
        self.original = {}
        for name in migration.CONFIG + migration.DATA:
            path = self.legacy.parent / name if name == ".env" else self.legacy / name
            if name in migration.FILES:
                path.write_text("fixture contents")
                path.chmod(0o664 if name == migration.ARCHIVE else 0o600)
            else:
                path.mkdir(mode=0o700)
                (path / "fixture").write_text("nested contents")
            self.original[path] = (path.stat().st_ino, path.stat().st_mode)

    def assert_old_paths(self):
        self.assertTrue(self.legacy.is_dir())
        for path, metadata in self.original.items():
            self.assertEqual((path.stat().st_ino, path.stat().st_mode), metadata)

    def migrate(self, action, **kwargs):
        return migration.migrate(self.repo, self.config, self.data, action, **kwargs)

    def test_dry_run_then_apply_then_restore_same_inodes(self):
        self.assertEqual(self.migrate("dry-run"), 12)
        self.assert_old_paths()
        self.assertFalse((self.config / migration.JOURNAL).exists())
        self.assertEqual(self.migrate("apply"), 12)
        self.assertFalse(self.legacy.exists())
        self.assertFalse((self.repo / "docker/.env").exists())
        self.assertEqual((self.data / "ise-work/fixture").read_text(), "nested contents")
        self.assertEqual(self.migrate("rollback"), 12)
        self.assert_old_paths()

    def test_reject_unknown_name(self):
        (self.legacy / "unknown").touch()
        with self.assertRaises(ValueError):
            self.migrate("dry-run")

    def test_reject_conflict(self):
        (self.config / ".env").touch()
        with self.assertRaises(ValueError):
            self.migrate("dry-run")

    def test_reject_symlink(self):
        key = self.legacy / "mcp-bearer"
        key.unlink()
        key.symlink_to(self.legacy / "tunnel-api-key")
        with self.assertRaises(ValueError):
            self.migrate("dry-run")

    def test_active_worker_and_setup_records_are_rejected(self):
        work = self.legacy / "ise-work"
        job = work / "worker/results/jobs/123/job.json"
        job.parent.mkdir(parents=True)
        worker_record = dict(exit_code=0, job_id="123", profile="fixture",
                             project="fixture", state="running")
        job.write_text(json.dumps(worker_record))
        with self.assertRaisesRegex(ValueError, "worker job"):
            self.migrate("dry-run")
        job.write_text(json.dumps(dict(worker_record, state="succeeded")))
        failed = job.parent.with_name("456") / "job.json"
        failed.parent.mkdir()
        failed.write_text(json.dumps(dict(worker_record, job_id="456", state="failed", exit_code=1)))
        setup = work / "install-state.json"
        setup.write_text('{"State":"running","Error":""}')
        with self.assertRaisesRegex(ValueError, "setup state"):
            self.migrate("dry-run")
        for record in ('{"State":"succeeded","Error":""}', '{"state":"succeeded","error":""}'):
            with self.subTest(record=record):
                setup.write_text(record)
                self.assertEqual(self.migrate("dry-run"), 12)
                self.assertEqual(setup.read_text(), record)

    def test_reject_invalid_setup_and_worker_state_records(self):
        work = self.legacy / "ise-work"
        setup = work / "install-state.json"
        job = work / "worker/results/jobs/private-job-id/job.json"
        for path, phase in ((setup, "ISE setup state"), (job, "ISE worker job")):
            path.parent.mkdir(parents=True, exist_ok=True)
            invalid = [
                (b'{"private-payload"', "invalid JSON"),
                (b'\xff', "invalid UTF-8"),
                (b'[]', "expected a JSON object"),
                (b'{}', "missing state field"),
                (b'{"state":[]}', "state field must be a string"),
                (b'{"state":"private-payload"}', "nonterminal or unknown state"),
                (b'{"state":"running","state":"succeeded"}', "duplicate fields"),
            ]
            if path == setup:
                invalid.append((b'{"State":"succeeded","state":"succeeded"}', "ambiguous"))
            else:
                invalid.append((b'{"State":"succeeded"}', "missing state field"))
            for contents, reason in invalid:
                with self.subTest(phase=phase, reason=reason):
                    path.write_bytes(contents)
                    with self.assertRaisesRegex(migration.ISEAdmissionError, f"{phase}.*{reason}") as caught:
                        self.migrate("dry-run")
                    self.assertNotIn("private-", str(caught.exception))
            path.unlink()
        with self.assertRaisesRegex(migration.ISEAdmissionError, "ISE worker job.*missing record"):
            self.migrate("dry-run")

    def test_rollback_for_failure_at_every_rename(self):
        for step in range(1, 13):
            with self.subTest(step=step):
                count = 0

                def fail_once(src, dst):
                    nonlocal count
                    count += 1
                    if count == step:
                        raise OSError("simulated rename failure")
                    os.rename(src, dst)

                with self.assertRaises(OSError):
                    self.migrate("apply", rename=fail_once)
                self.assert_old_paths()

    def test_recover_an_interrupted_rename_before_completion_record(self):
        class Interrupted(BaseException):
            pass

        def crash(src, dst):
            os.rename(src, dst)
            raise Interrupted

        with self.assertRaises(Interrupted):
            self.migrate("apply", rename=crash)
        self.migrate("rollback")
        self.assert_old_paths()


if __name__ == "__main__":
    unittest.main()
