"""Synthetic storage and supervisor state tests for an external cutover."""
from pathlib import Path
import os
import socket
import tempfile
from types import SimpleNamespace
import subprocess
import unittest
from unittest.mock import patch

from cutover_copy import copy_external, entries, manifest, restore_legacy
from cutover_remote import Cutover, INGRESS, load_script, restart_value


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = load_script(ROOT, "migrate-external-storage")
API = load_script(ROOT, "cutover-external-storage")


class TransferTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.docker = root / "checkout/docker"
        self.legacy = self.docker / "private"
        self.config = root / "config"
        self.data = root / "data"
        self.stage = self.docker / ".restore"
        for directory in (self.legacy, self.config, self.data):
            directory.mkdir(parents=True, mode=0o700)
        self.plan = [
            (self.docker / ".env", self.config / ".env"),
            (self.legacy / "workspace", self.data / "workspace"),
            (self.legacy / "repo-rpc", self.data / "repo-rpc"),
        ]
        env, workspace, rpc = [old for old, _ in self.plan]
        env.write_text("synthetic")
        env.chmod(0o600)
        workspace.mkdir()
        rpc.mkdir()
        payload = workspace / "payload"
        payload.write_bytes(b"data")
        payload.chmod(0o640)
        os.setxattr(payload, "user.synthetic", b"metadata")
        os.link(payload, rpc / "linked")
        (workspace / "relative").symlink_to("../repo-rpc/linked")

    def test_copy_omits_only_known_socket_and_preserves_metadata(self):
        sock = self.legacy / "repo-rpc/panolab-git.sock"
        with socket.socket(socket.AF_UNIX) as gateway:
            gateway.bind(str(sock))
        digest = copy_external(self.plan)
        self.assertTrue(sock.is_socket())
        self.assertFalse((self.data / "repo-rpc/panolab-git.sock").exists())
        self.assertEqual(digest, manifest(entries(self.plan, True)))
        self.assertTrue((self.data / "workspace/payload").samefile(self.data / "repo-rpc/linked"))

    def test_interrupted_deletion_and_restore_can_recover(self):
        digest = copy_external(self.plan)
        self.plan[0][0].unlink()
        (self.legacy / "workspace/payload").unlink()
        rename = MIGRATION.rename_without_replacement
        restore_legacy(self.plan, self.stage, digest, rename, self.legacy, "restoring")
        rename(self.stage / ".env", self.docker / ".env")
        restore_legacy(self.plan, self.stage, digest, rename, self.legacy, "installing-restore")
        self.assertEqual(digest, manifest(entries(self.plan, False)))
        restore_legacy(self.plan, self.stage, digest, rename, self.legacy, "installing-restore")
        self.assertEqual(digest, manifest(entries(self.plan, True)))

    def test_corrupt_external_copy_does_not_remove_originals(self):
        digest = copy_external(self.plan)
        (self.data / "workspace/payload").write_bytes(b"corrupted")
        with self.assertRaisesRegex(ValueError, "identity differs"):
            restore_legacy(self.plan, self.stage, digest, MIGRATION.rename_without_replacement,
                           self.legacy, "restoring")
        self.assertEqual(manifest(entries(self.plan, False)), digest)

    def test_uninventoried_hardlink_and_old_absolute_symlink_are_rejected(self):
        old = self.legacy / "workspace"
        outside = old.parent / "outside"
        os.link(old / "payload", outside)
        with self.assertRaisesRegex(ValueError, "outside inventoried"):
            copy_external(self.plan)
        outside.unlink()
        (old / "wrong").symlink_to(old / "payload")
        with self.assertRaisesRegex(ValueError, "target changes"):
            copy_external(self.plan)
        self.assertFalse(any(self.data.iterdir()))


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        args = SimpleNamespace(
            checkout=root / "repo", config=root / "config", data=root / "data",
            socket=root / "sock", journal=root / "journal", target="a" * 40,
            baseline="b" * 40, transaction="0" * 32, inventory_sha256="f" * 64,
            broker_image=["broker:test", "broker"], repo_git_image=["repo:test", "repo"],
        )
        args.journal.mkdir()
        self.records = {
            name: {"id": f"old-{i}", "image_id": f"image-{i}", "mounts": [],
                   "restart": {"Name": "no", "MaximumRetryCount": 0}}
            for i, name in enumerate(API.SERVICE_TAGS)
        }
        self.operation = Cutover(API, args, self.records, MIGRATION, None)

    def test_recover_only_exact_labeled_replacement(self):
        tx = self.operation
        names = {INGRESS: "foreign", API.DEV: self.records[API.DEV]["id"]}
        with patch.object(tx, "containers", return_value=names), patch.object(tx, "docker") as docker:
            docker.return_value = "unrelated"
            with self.assertRaisesRegex(ValueError, "foreign container"):
                tx.owned()
            docker.return_value = tx.args.transaction
            self.assertEqual(tx.owned(), {INGRESS: "foreign"})
            self.assertTrue(all(call.args[0] == "inspect" for call in docker.call_args_list))

    def test_ingress_stops_first_and_known_ids_are_retained(self):
        tx = self.operation
        with patch.object(tx, "docker", return_value="exited") as docker, patch.object(tx, "quiescent"), patch.object(
            MIGRATION, "require_terminal_ise_jobs",
        ):
            tx.stop_old()
        actions = [call.args for call in docker.call_args_list]
        stops = [cmd[-1] for cmd in actions if cmd[0] == "stop"]
        self.assertEqual(stops, [self.records[name]["id"] for name in tx.stop_order])
        self.assertEqual(stops[0], self.records[INGRESS]["id"])
        self.assertNotIn("rm", [cmd[0] for cmd in actions])

    def test_open_ingress_only_after_local_health(self):
        tx = self.operation
        tx.legacy.mkdir(parents=True)
        tx.state = {"supervisor": "supervisor"}
        replacement = {name: f"new-{name}" for name in tx.names}
        events = []

        def docker(*command):
            events.append(command)
            if command == ("inspect", "--format", "{{.State.Status}}", replacement[INGRESS]):
                return "running"
            if command[0] == "inspect":
                name = next(name for name, saved in self.records.items() if saved["id"] == command[-1])
                return f"{self.records[name]['image_id']}|/{tx.renamed(name)}|exited|no"
            return ""

        def replacement_image(*command):
            if command[0] == "inspect" and command[2] == "{{.Image}}":
                name = next(name for name, oid in replacement.items() if oid == command[-1])
                return {"panolab-direct-connect-docker-broker-1": tx.args.broker_image[1],
                        "panolab-direct-connect-repo-git-1": tx.args.repo_git_image[1]}.get(
                            name, self.records[name]["image_id"])
            return docker(*command)

        with (
            patch.object(tx, "git"),
            patch.object(tx, "docker", side_effect=replacement_image),
            patch.object(API, "require_checkout"),
            patch.object(API, "query"),
            patch.object(tx, "stop_old"),
            patch.object(tx, "create_replacements"),
            patch.object(tx, "owned", return_value=replacement),
            patch.object(tx, "storage_identity", return_value={}),
            patch.object(tx, "plan", []),
            patch("cutover_remote.copy_external", return_value="verified"),
            patch.object(tx, "probe", side_effect=lambda ids: events.append(("probe", ids))),
        ):
            tx.apply()
        self.assertLess(events.index(("probe", replacement)),
                        events.index(("start", replacement[INGRESS])))
        self.assertEqual(tx.state["phase"], "completed")

    def test_local_git_rollback_restores_development_ref(self):
        tx = self.operation
        tx.repo.mkdir()

        def git(*args):
            return subprocess.check_output(
                ["git", "-C", str(tx.repo), *args], stderr=subprocess.DEVNULL, text=True,
            ).strip()

        git("init", "-b", "development")
        git("config", "user.email", "synthetic@example.invalid")
        git("config", "user.name", "Synthetic cutover test")
        payload = tx.repo / "source"
        payload.write_text("baseline")
        git("add", "source")
        git("commit", "-m", "Baseline")
        tx.args.baseline = git("rev-parse", "HEAD")
        git("branch", "--copy", "development", tx.baseline_branch)
        payload.write_text("reviewed")
        git("commit", "-am", "Reviewed")
        tx.args.target = git("rev-parse", "HEAD")

        tx.restore_source()
        tx.restore_source()
        self.assertEqual(git("symbolic-ref", "--short", "HEAD"), "development")
        self.assertEqual(git("rev-parse", "HEAD"), tx.args.baseline)
        self.assertEqual(payload.read_text(), "baseline")
        self.assertEqual(git("status", "--porcelain"), "")
        self.assertEqual(git("rev-parse", tx.target_branch), tx.args.target)

    def test_restart_policy_round_trip(self):
        self.assertEqual(restart_value({"Name": "on-failure", "MaximumRetryCount": 7}), "on-failure:7")
        with self.assertRaises(ValueError):
            restart_value({"Name": "always", "MaximumRetryCount": 1})
