"""Exercise the CLI against a gated synthetic Codex executable."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
FAKE_CODEX = r"""
import os
from pathlib import Path
import signal
import sys
import time

assert sys.argv[1:5] == [
    "exec", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox",
    "--output-last-message",
]
assert sys.argv[6:] == ["-"]
Path("received").write_bytes(sys.stdin.buffer.read())
print("combined stdout", flush=True)
print("combined stderr", file=sys.stderr, flush=True)
Path("ready.tmp").write_text(str(os.getppid()))
Path("ready.tmp").rename("ready")
deadline = time.monotonic() + 15
while not Path("release").exists():
    if time.monotonic() >= deadline:
        sys.exit(99)
    time.sleep(0.01)
if os.environ["FAKE_VERDICT"]:
    Path(sys.argv[5]).write_text(os.environ["FAKE_VERDICT"] + "\n")
Path("done").touch()
if os.environ["FAKE_EXIT"] == "signal":
    os.kill(os.getpid(), signal.SIGTERM)
sys.exit(int(os.environ["FAKE_EXIT"]))
"""


class LauncherTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=HERE)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.launcher = self.root / "launcher.py"
        repo = self.root / "repo"
        repo.mkdir()
        self.policy = repo / "AGENTS.md"
        self.policy.write_bytes(b"# Fixture policy\r\nExact canonical bytes.\n")
        source = (HERE / "launcher.py").read_text().replace(
            'REPO = Path("/repo")',
            f"REPO = Path({str(repo)!r})",
        )
        self.launcher.write_text(source)
        self.manifest = self.root / "manifest.json"
        self.required = self.root / "required.txt"
        self.required.write_text("required source")
        self.required_dir = self.root / "required-dir"
        self.required_dir.mkdir()
        self.declaration = dict(
            files=[dict(path=str(self.required),
                        sha256=hashlib.sha256(self.required.read_bytes()).hexdigest())],
            directories=[str(self.required_dir)], executables=["codex"],
        )
        self.write_manifest()
        self.prompt = self.root / "source.txt"
        self.prompt.write_bytes(b"original prompt\n")
        self.workdir = self.root / "work"
        self.workdir.mkdir()
        fake = self.root / "codex"
        fake.write_text(f"#!{sys.executable}\n" + FAKE_CODEX)
        fake.chmod(0o700)
        self.env = dict(os.environ, PATH=f"{self.root}:{os.environ['PATH']}")
        self.env["FAKE_VERDICT"] = '{"outcome":"COMPLETED"}'
        self.job_id = None
        self.addCleanup(self.release_job)

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if result := predicate():
                return result
            time.sleep(0.025)
        self.fail("condition did not become true")

    def release_job(self):
        (self.workdir / "release").touch()
        if self.job_id and (self.workdir / "ready").exists():
            self.wait_for(lambda: (self.workdir / "done").exists())
            self.wait_for(lambda: self.status()["state"] != "running")

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(self.launcher), *map(str, args)],
            env=self.env, capture_output=True, text=True, timeout=5,
        )

    def write_manifest(self):
        self.manifest.write_text(json.dumps(self.declaration))

    def start_job(self, workdir=None, prompt=None):
        return self.cli("start", "--workdir", workdir or self.workdir,
                        "--prompt-file", prompt or self.prompt, "--prerequisites", self.manifest)

    def launch(self, exit_code):
        self.env["FAKE_EXIT"] = str(exit_code)
        result = self.start_job()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.job_id = result.stdout.strip()
        self.assertRegex(self.job_id, r"^[0-9a-f]{32}$")
        self.job = self.root / "jobs" / self.job_id
        self.wait_for(lambda: (self.workdir / "ready").exists())
        self.assertFalse((self.workdir / "release").exists())

    def status(self, command="status"):
        result = self.cli(command, self.job_id)
        status = json.loads(result.stdout)
        blocked = status.get("infrastructure_verdict") == "INFRASTRUCTURE_BLOCKED"
        self.assertEqual(result.returncode, 2 if blocked else 0, result.stderr)
        if blocked:
            self.assertTrue(result.stderr.startswith("INFRASTRUCTURE_BLOCKED "))
        return status

    def finish(self):
        (self.workdir / "release").touch()
        def finished():
            result = self.status("result")
            return result if result["state"] != "running" else None
        return self.wait_for(finished)

    def test_detached_running_and_success(self):
        self.launch(0)
        running = self.status()
        self.assertEqual(running["state"], "running")
        self.assertEqual(self.status("result")["state"], "running")
        self.assertIsNone(running["exit_code"])
        self.assertIsNone(running["finished_at"])
        self.prompt.write_text("edited prompt")
        received = (self.workdir / "received").read_bytes()
        self.assertTrue(received.startswith(self.policy.read_bytes() + b"\n\n"))
        self.assertTrue(received.endswith(b"original prompt\n"))
        self.assertEqual((self.job / "prompt.txt").read_bytes(), received)
        self.assertEqual(running["policy_sha256"], hashlib.sha256(self.policy.read_bytes()).hexdigest())
        self.assertEqual((self.job / "prompt.txt").stat().st_mode & 0o777, 0o400)
        self.assertEqual(json.loads((self.job / "status.json").read_text())["workdir"],
                         str(self.workdir))

        response = self.cli("tail", self.job_id, "--bytes", 16)
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertNotIn("combined", response.stdout)
        snapshot = json.loads(response.stdout)
        self.assertEqual(snapshot["bytes"], 16)
        self.assertEqual(Path(snapshot["tail_file"]).read_bytes(), b"combined stderr\n")

        result = self.finish()
        self.assertEqual((result["state"], result["exit_code"]), ("succeeded", 0))
        self.assertEqual(result["engineering_outcome"], "COMPLETED")
        self.assertIsNone(result["infrastructure_verdict"])
        self.assertEqual((self.job / result["log_file"]).read_bytes(),
                         b"combined stdout\ncombined stderr\n")
        self.assertLessEqual(result["created_at"], result["started_at"])
        self.assertLessEqual(result["started_at"], result["finished_at"])
        self.assertTrue(result["finished_at"].endswith("+00:00"))

    def test_failure_preserves_exit_code(self):
        self.launch(37)
        result = self.finish()
        self.assertEqual((result["state"], result["exit_code"]), ("failed", 37))

    def test_signal_preserves_process_return_code(self):
        self.launch("signal")
        result = self.finish()
        self.assertEqual((result["state"], result["exit_code"]),
                         ("failed", -signal.SIGTERM))

    def test_lost_supervisor(self):
        self.launch(0)
        supervisor = int((self.workdir / "ready").read_text())
        os.kill(supervisor, signal.SIGKILL)

        def lost():
            result = self.status("result")
            return result if result["state"] == "lost" else None

        result = self.wait_for(lost)
        self.assertEqual(result["infrastructure_verdict"], "INFRASTRUCTURE_BLOCKED")
        self.assertIsNone(result["exit_code"])
        self.assertIsNone(result["finished_at"])
        self.assertEqual(self.finish()["state"], "lost")

    def assert_admission_block(self, resource, result=None):
        result = self.start_job() if result is None else result
        self.assertEqual(result.returncode, 2, result.stderr)
        prefix = "INFRASTRUCTURE_BLOCKED "
        self.assertTrue(result.stderr.startswith(prefix), result.stderr)
        details = json.loads(result.stderr[len(prefix):])
        self.assertEqual(details["resource"], str(resource))
        self.assertTrue(details["last_step"])
        self.assertEqual(result.stdout, "")
        self.assertFalse((self.root / "jobs").exists())
        self.assertFalse((self.workdir / "ready").exists())
        return details

    def test_missing_executable(self):
        self.declaration["executables"].append("no-such-panolab-tool")
        self.write_manifest()
        self.assert_admission_block("no-such-panolab-tool")

    def test_missing_codex(self):
        self.env["PATH"] = str(self.root / "missing")
        self.assert_admission_block("codex")

    def test_missing_file(self):
        self.required.unlink()
        self.assert_admission_block(self.required)

    def test_missing_directory(self):
        self.required_dir.rmdir()
        self.assert_admission_block(self.required_dir)

    def test_file_permissions(self):
        self.required.chmod(0)
        self.assert_admission_block(self.required)

    def test_directory_permissions(self):
        self.required_dir.chmod(0o600)
        self.assert_admission_block(self.required_dir)

    def test_bad_digest(self):
        self.required.write_text("changed")
        self.assertIn("expected SHA-256", self.assert_admission_block(self.required)["error"])

    def test_malformed_manifest(self):
        self.manifest.write_text('{"files":[],"files":[],"directories":[],"executables":[]}')
        self.assertIn("duplicate JSON key", self.assert_admission_block(self.manifest)["error"])

    def test_absent_manifest(self):
        self.manifest.unlink()
        self.assert_admission_block(self.manifest)

    def test_missing_declaration_argument(self):
        result = self.cli("start", "--workdir", self.workdir, "--prompt-file", self.prompt)
        self.assert_admission_block("--prerequisites", result)

    def test_absent_prompt(self):
        self.prompt.unlink()
        self.assert_admission_block(self.prompt)

    def test_absent_root_policy_blocks(self):
        self.policy.unlink()
        self.assert_admission_block(self.policy)

    def test_worker_infrastructure_verdict(self):
        expected = dict(resource="/repo/spec", error="absent", last_step="read policy",
                        stopped_work="verification")
        self.env["FAKE_VERDICT"] = json.dumps(dict(expected, outcome="INFRASTRUCTURE_BLOCKED"))
        self.launch(0)
        result = self.finish()
        self.assertEqual(result["state"], "succeeded")
        self.assertEqual(result["infrastructure_blocker"], expected)
        self.assertIsNone(result["engineering_outcome"])

    def test_missing_worker_verdict(self):
        self.env["FAKE_VERDICT"] = ""
        self.launch(0)
        result = self.finish()
        self.assertEqual(result["state"], "succeeded")
        self.assertEqual(result["reason"], "invalid_or_missing_worker_verdict")
        self.assertIsNone(result["engineering_outcome"])

    def test_historical_terminal_status_is_preserved(self):
        self.job_id = "a" * 32
        job = self.root / "jobs" / self.job_id
        job.mkdir(parents=True)
        (job / "supervisor.lock").touch()
        old_status = dict(job_id=self.job_id, state="succeeded", exit_code=0, reason=None)
        (job / "status.json").write_text(json.dumps(old_status))
        (job / "codex.log").write_text("historical log")
        self.assertEqual(self.status(), old_status)
        self.assertEqual(json.loads((job / "status.json").read_text()), old_status)
        self.assertEqual((job / "codex.log").read_text(), "historical log")

    def test_policy_drift_prevents_codex_spawn(self):
        spec = importlib.util.spec_from_file_location("fixture_launcher", self.launcher)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.dict(os.environ, self.env), patch.object(module.subprocess, "Popen") as spawn:
            self.job_id = module.start(self.workdir, self.prompt, self.manifest)
            spawn.assert_called_once()
            job = module.job_directory(self.job_id)
            self.policy.write_text("policy changed after initial admission")
            spawn.reset_mock()
            module.supervise(self.job_id, os.open(job / "supervisor.lock", os.O_RDONLY))
            spawn.assert_not_called()
        result = self.status()
        self.assertEqual(result["state"], "interrupted")
        self.assertEqual(result["infrastructure_blocker"]["resource"], str(self.policy))
        self.assertIn("changed", result["infrastructure_blocker"]["error"])

    def test_rejects_paths_outside_workspace_and_invalid_job_id(self):
        outside = self.root / "outside"
        outside.symlink_to("/")
        self.assert_admission_block(outside, self.start_job(workdir=outside))
        self.assert_admission_block(outside, self.start_job(prompt=outside))
        self.assertEqual(self.cli("result", "../bootstrap-001").returncode, 2)


if __name__ == "__main__":
    unittest.main()
