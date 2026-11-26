"""Read-only cutover checks against synthetic Git and Docker responses."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "cutover", Path(__file__).with_name("cutover-external-storage.py"))
cutover = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cutover)


class CutoverPreflightTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.repo, self.source, self.config, self.data = [
            root / name for name in ("repo", "source", "config", "data")
        ]
        for path in (self.repo, self.source):
            (path / ".git").mkdir(parents=True)
        for path in (self.config, self.data):
            path.mkdir(mode=0o700)
        self.sock = root / "docker.sock"
        self.args = SimpleNamespace(
            checkout=self.repo, baseline="a"*40, target="b"*40,
            inventory=root / "inventory.json",
            broker_image=("panolab-direct-broker:candidate", "sha256:" + "b"*64),
            repo_git_image=("panolab-direct-repo-git:candidate", "sha256:" + "c"*64),
        )
        self.records = {
            name: {"id": f"{index:064x}", "image_id": f"sha256:{index:064x}",
                   "state": "running" if name in cutover.RUNNING else "exited",
                   "restart": {"Name": "unless-stopped" if name in cutover.RUNNING else "no",
                               "MaximumRetryCount": 0},
                   "mounts": []}
            for index, name in enumerate([*cutover.SERVICE_TAGS, *[f"backup-{n}" for n in range(4)]], 1)
        }
        self.records[cutover.DEV]["mounts"] = [
            {"type": "bind", "target": "/repo/agent", "rw": True, "canonical_relative": "agent"},
        ]
        payload = json.dumps({"containers": self.records}).encode()
        self.args.inventory.write_bytes(payload)
        self.args.inventory.chmod(0o600)
        self.args.inventory_sha256 = hashlib.sha256(payload).hexdigest()
        self.by_id = {entry["id"]: (name, entry) for name, entry in self.records.items()}
        self.tags = {tag: self.records[name]["image_id"] for name, tag in cutover.SERVICE_TAGS.items()}
        self.tags.update([self.args.broker_image, self.args.repo_git_image])
        self.calls = []
        self.foreign = False
        self.fail_inspect = False

    def run_command(self, *args):
        self.calls.append(args)
        program, *command = args
        if program == "git":
            _, _, path, *action = command
            revision = self.args.baseline if path == str(self.repo) else self.args.target
            return {
                ("rev-parse", "HEAD"): revision,
                ("status", "--porcelain=v1", "--untracked-files=all"): "",
                ("symbolic-ref", "--short", "HEAD"): "development",
                ("rev-parse", "refs/remotes/origin/development"): self.args.target,
                ("merge-base", "--is-ancestor", self.args.baseline, self.args.target): "",
            }[tuple(action)]
        if program == "python3":
            self.assertIn(Path(command[1]).name, {"dev_source.py", "migrate-external-storage.py"})
            return ""
        self.assertEqual((program, *command[:2]), ("docker", "-H", f"unix://{self.sock}"))
        verb, *rest = command[2:]
        if verb == "info":
            return {"{{json .SecurityOptions}}": '["name=rootless"]',
                    "{{.CgroupDriver}}/{{.CgroupVersion}}": "systemd/2"}[rest[-1]]
        if verb == "compose":
            self.assertEqual(rest, ["version"])
            return ""
        if verb == "ps":
            return "\n".join([*self.by_id, *(["foreign"] if self.foreign else [])])
        if verb == "inspect":
            if self.fail_inspect:
                raise subprocess.CalledProcessError(1, "docker inspect")
            name, entry = self.by_id[rest[-1]]
            mounts = [{"Type": "bind", "Destination": "/repo/agent", "RW": True,
                       "Source": str(self.repo / "agent")}] if name == cutover.DEV else []
            return "|".join(map(json.dumps, (entry["id"], "/" + name, entry["image_id"],
                                             entry["state"], entry["restart"], mounts)))
        if verb == "image" and rest[0] == "inspect":
            return self.tags[rest[-1]]
        self.fail(f"Unexpected operation {verb}")

    def preflight(self):
        with patch.object(cutover, "SOURCE", self.source), patch.dict("os.environ", {
            "PANOLAB_CONFIG_DIR": str(self.config), "PANOLAB_DATA_DIR": str(self.data),
        }):
            cutover.preflight(self.args, self.sock, self.run_command)

    def test_source_and_container_checks_precede_migration_dry_run(self):
        self.preflight()
        self.assertIn("merge-base", self.calls[4])
        self.assertEqual(self.calls[-1][-3:], ("dry-run", "--checkout", str(self.repo)))
        inspected = {call[-1] for call in self.calls if call[0] == "docker" and call[3] == "inspect"}
        self.assertEqual(inspected, set(self.by_id))

    def test_foreign_container_stops_before_migration(self):
        self.foreign = True
        with self.assertRaisesRegex(ValueError, "container set differs"):
            self.preflight()
        self.assertFalse(any("dry-run" in call for call in self.calls))

    def test_nonempty_external_root_stops_before_docker(self):
        (self.config / ".env").touch()
        with self.assertRaisesRegex(ValueError, "must be empty"):
            self.preflight()
        self.assertFalse(any(call[0] == "docker" for call in self.calls))

    def test_failed_inspection_leaves_original_ids_and_allows_fresh_preflight(self):
        self.fail_inspect = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.preflight()
        self.assertFalse(any("dry-run" in call for call in self.calls))
        self.fail_inspect = False
        self.preflight()
        self.assertEqual(set(self.by_id), {record["id"] for record in self.records.values()})
