"""Offline tests of broker RPC handlers and the rootless upgrade script."""
import ast
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DEV = "panolab-direct-dev-1"
RELS = ("projects", "boards", "shared", "third_party", "research", "agent",
        "specs", "tests", "docs", "host", "docker/modern")


def layout(root, workspace, auth, case):
    paths = [(workspace, "/workspace", True), (auth, "/codex-auth", True)]
    for rel in RELS:
        if rel == "research" and case in ("previous", "legacy"):
            continue
        if case == "legacy" and rel in ("projects", "shared", "third_party"):
            continue
        paths.append((f"{root}/{rel}", f"/repo/{rel}",
                      rel == "agent" or (rel == "research" and case == "writable")))
    if case == "legacy":
        paths.append((f"{root}/gateware", "/repo/gateware", True))
    if case == "wrong_source":
        paths[6] = (f"{root}/other", "/repo/research", False)
    if case == "private":
        paths.append((f"{root}/docker/private", "/repo/docker/private", False))
    mounts = [dict(Type="bind", Source=src, Destination=dst, RW=rw)
              for src, dst, rw in paths]
    if case == "unexpected_type":
        mounts.append(dict(Type="volume", Destination="/repo/.git"))
    return mounts


class BrokerResearchMountTests(unittest.TestCase):
    def setUp(self):
        # Load definitions only. The script's top-level server never starts.
        tree = ast.parse((ROOT / "docker/control/broker.py").read_text())
        functions = {"image_allowed", "launch_dev", "repo_configured",
                     "verify_dev_sources", "migrate_dev", "dispatch"}
        constants = {"SOURCE_MOUNTS", "DEV", "STAGE", "BACKUP", "IMAGES"}
        tree.body = [node for node in tree.body if
                     (isinstance(node, ast.FunctionDef) and node.name in functions)
                     or (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                         and node.targets[0].id in constants)]
        self.calls = []
        self.mounts = {}
        self.running = True
        self.policy = {"Name": "on-failure", "MaximumRetryCount": 3}
        self.approved_image = "sha256:original"
        self.probe_failure = None
        self.context = dict(json=json, os=os, command=self.command, REPO="/canonical",
                            W="/work", CODEX_AUTH="/auth", CONTAINER_DEV_USER="0:0")
        exec(compile(tree, "broker definitions", "exec"), self.context)
        self.dispatch = self.context["dispatch"]

    def command(self, argv, timeout):
        call = argv[1:]
        self.calls.append(call)
        op = call[0]
        name = call[-1]
        if op == "inspect":
            if name not in self.mounts:
                return dict(ok=False)
            if len(call) == 2:
                return dict(ok=True)
            output = (json.dumps(self.mounts[name]) if ".Mounts" in call[2] else
                      f'true|{str(self.running).lower()}|'
                      f'{json.dumps(self.policy)}|sha256:original')
            return dict(ok=True, stdout=output)
        if op == "image":
            return dict(ok=True, stdout=self.approved_image)
        if op == "run":
            mounts = []
            for i, item in enumerate(call):
                if item == "--mount":
                    _, source, target, *mode = call[i+1].split(",")
                    mounts.append(dict(Type="bind", Source=source[4:],
                                       Destination=target[4:], RW=not mode))
            self.mounts[call[call.index("--name")+1]] = mounts
        elif op == "rename":
            self.mounts[name] = self.mounts.pop(call[1])
        elif op == "rm":
            self.mounts.pop(name, None)
        elif op == "exec":
            return dict(ok=call[3] != self.probe_failure)
        elif op not in ("start", "stop", "update"):
            raise AssertionError(call)
        return dict(ok=True)

    def test_create_only_approved_binds_and_restart_policy(self):
        self.assertTrue(self.dispatch({"action": "create"})["ok"])
        self.assertEqual(self.mounts[DEV], layout("/canonical", "/work", "/auth", "current"))
        run = next(call for call in self.calls if call[0] == "run")
        self.assertEqual(run[run.index("--restart")+1], "unless-stopped")

    def test_attach_repairs_missing_wrong_or_extra_mounts(self):
        for case in ("previous", "writable", "wrong_source", "private", "unexpected_type"):
            with self.subTest(case=case):
                self.calls.clear()
                old = layout("/canonical", "/work", "/auth", case)
                self.mounts = {DEV: old}
                result = self.dispatch({"action": "attach_checkout"})
                self.assertTrue(result["migrated"])
                self.assertEqual(self.mounts[result["rollback"]], old)
                self.assertEqual(self.mounts[DEV], layout("/canonical", "/work", "/auth", "current"))
                stage, active = [call for call in self.calls if call[0] == "run"]
                self.assertEqual(stage[stage.index("--restart")+1], "no")
                self.assertEqual(active[active.index("--restart")+1], "on-failure:3")
                self.assertEqual(active[-3], "sha256:original")
                for probe in (call[-1] for call in self.calls if call[0] == "exec"):
                    for path in ("/repo/docker/private", "/repo/docker/.env", "/repo/.git"):
                        self.assertIn("test ! -e " + path, probe)

    def test_attach_already_current_leaves_dev_alone(self):
        self.mounts[DEV] = layout("/canonical", "/work", "/auth", "current")
        self.assertTrue(self.dispatch({"action": "attach_checkout"})["already_configured"])
        self.assertEqual([call[0] for call in self.calls], ["inspect", "inspect"])

    def test_failed_stage_leaves_live_dev_alone(self):
        self.mounts[DEV] = layout("/canonical", "/work", "/auth", "previous")
        self.probe_failure = self.context["STAGE"]
        self.assertFalse(self.dispatch({"action": "attach_checkout"})["ok"])
        self.assertEqual(list(self.mounts), [DEV])
        self.assertNotIn(["stop", DEV], self.calls)

    def test_failed_replacement_restores_original_state(self):
        for running in (True, False):
            with self.subTest(running=running):
                self.calls.clear()
                self.running = running
                old = layout("/canonical", "/work", "/auth", "previous")
                self.mounts = {DEV: old}
                self.probe_failure = DEV
                result = self.dispatch({"action": "attach_checkout"})
                self.assertFalse(result["ok"])
                self.assertTrue(result["original_restored"])
                self.assertEqual(self.mounts, {DEV: old})
                self.assertEqual(["start", DEV] in self.calls, running)

    def test_attach_preserves_always_policy_without_restarting_rollback_on_reboot(self):
        self.policy = {"Name": "always", "MaximumRetryCount": 0}
        self.mounts[DEV] = layout("/canonical", "/work", "/auth", "previous")
        result = self.dispatch({"action": "attach_checkout"})
        self.assertTrue(result["ok"])
        active = [call for call in self.calls if call[0] == "run"][-1]
        self.assertEqual(active[active.index("--restart")+1], "always")
        self.assertIn(["update", "--restart", "no", result["rollback"]], self.calls)

    def test_attach_does_not_default_to_a_different_or_unapproved_image(self):
        self.mounts[DEV] = layout("/canonical", "/work", "/auth", "previous")
        self.approved_image = "sha256:different"
        with self.assertRaisesRegex(ValueError, "differs from the approved modern image"):
            self.dispatch({"action": "attach_checkout"})
        with self.assertRaisesRegex(ValueError, "outside approved catalog"):
            self.dispatch({"action": "attach_checkout", "image": "custom:latest"})
        self.assertTrue(all(call[0] in ("inspect", "image") for call in self.calls))

    def test_successful_attach_preserves_stopped_state(self):
        self.running = False
        self.mounts[DEV] = layout("/canonical", "/work", "/auth", "previous")
        self.assertTrue(self.dispatch({"action": "attach_checkout"})["ok"])
        self.assertEqual(self.calls.count(["stop", DEV]), 1)
        self.assertEqual(self.calls[-1], ["stop", DEV])


HOST_MOCK = r"""
id() { echo 1000; }
docker() {
  shift 2  # Mock Docker's rootless socket option.
  printf '%s\n' "$*" >> "$MOCK_LOG"
  case "$1 $2" in
    'info --format') echo '["name=rootless"]';;
    'container inspect') [[ "$3" == "$DEV" && "$CASE" != absent ]];;
    "inspect $DEV") cat "$MOCK_INSPECT";;
    'inspect -f')
      case "$3" in
        *'State.Running'*) echo true;;
        *'State.Status'*) echo "$ROLLBACK_STATE|true";;
        *'.Image'*) echo sha256:current;;
        *'/repo/research'*) echo "bind|$MOCK_ROOT/research|$REPLACEMENT_WRITABLE";;
        *) return 99;;
      esac;;
    'image inspect')
      case "$4" in
        *'.Id'*) echo sha256:current;;
        *) echo modern-unified-dev-20261123-v2;;
      esac;;
    'ps -a')
      if [[ "$HAS_ROLLBACK" == yes ]]; then
        echo panolab-direct-dev-1-rollback-20261124T064116Z
      fi;;
    'exec panolab-direct-dev-1')
      case "${4:-}" in
        /sys/fs/cgroup/cpu.max) echo '200000 100000';;
        /sys/fs/cgroup/memory.max) echo 4294967296;;
        /sys/fs/cgroup/pids.max) echo 256;;
      esac;;
    'run --rm'|'run -d'|'exec -e'|"stop -t"|"rename $DEV"|rm*|start*|rename*) :;;
    *) echo "Unexpected mock command: $*" >&2; return 99;;
  esac
}
export -f id docker
exec bash "$@"
"""


class HostResearchUpgradeTests(unittest.TestCase):
    def run_upgrade(self, case, has_rollback=False, rollback_state="exited",
                    replacement_writable=False):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repo, work, auth = (base / name for name in ("repo", "work", "auth"))
            for path in (work, auth, repo / ".git", *(repo / rel for rel in RELS)):
                path.mkdir(parents=True)
            inspect = base / "inspect.json"
            inspect.write_text(json.dumps([{
                "Config": {"Labels": {"panolab.managed": "true"}, "User": "0:0",
                           "WorkingDir": "/workspace", "Env": ["CODEX_HOME=/codex-auth"]},
                "HostConfig": {"Privileged": False, "SecurityOpt": ["no-new-privileges:true"],
                               "CapDrop": ["ALL"]},
                "Mounts": layout(repo, str(work), str(auth), case),
            }]))
            log = base / "calls"
            sock = str(base / "fake.sock")
            with socket.socket(socket.AF_UNIX) as fixture:
                fixture.bind(sock)
                result = subprocess.run(
                    ["bash", "-c", HOST_MOCK, "mock",
                     str(ROOT / "host/upgrade-dev-image.sh"),
                     str(repo), sock, str(work), str(auth)],
                    env={**os.environ, "DEV": DEV, "CASE": case,
                         "ROLLBACK_STATE": rollback_state,
                         "REPLACEMENT_WRITABLE": str(replacement_writable).lower(),
                         "HAS_ROLLBACK": "yes" if has_rollback else "no",
                         "MOCK_LOG": str(log), "MOCK_INSPECT": str(inspect),
                         "MOCK_ROOT": str(repo)},
                    text=True, capture_output=True, check=False,
                )
            return result, log.read_text()

    def test_create_or_migrate_supported_layouts(self):
        for case, prior in (("absent", False), ("legacy", False), ("previous", True)):
            with self.subTest(case=case):
                result, calls = self.run_upgrade(case, prior)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("DEV_UPGRADE_RESULT=PASS", result.stdout)
                run = next(line for line in calls.splitlines() if line.startswith("run -d"))
                self.assertIn("dst=/repo/research,readonly", run)
                self.assertIn("--restart unless-stopped", run)
                self.assertTrue(run.endswith("sha256:current sleep infinity"))
                for path in ("/repo/docker/private", "/repo/docker/.env", "/repo/.git", "dst=/repo "):
                    self.assertNotIn(path, run)
                    if path != "dst=/repo ":
                        self.assertIn("test ! -e " + path, calls)
                self.assertNotIn("\nrm ", calls)
                self.assertNotIn("\nrename panolab-direct-dev-1-rollback-", calls)
                if case != "absent":
                    self.assertIn("ROLLBACK_CONTAINER=", result.stdout)

    def test_current_layout_returns_without_replacement(self):
        result, calls = self.run_upgrade("current", True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DEV_IMAGE_AND_SOURCE_MOUNTS_ALREADY_CURRENT=1", result.stdout)
        self.assertNotIn("\nstop ", calls)
        self.assertNotIn("\nrun -d", calls)

    def test_unexpected_layout_is_rejected_before_mutation(self):
        for case in ("writable", "wrong_source", "private", "unexpected_type"):
            with self.subTest(case=case):
                result, calls = self.run_upgrade(case)
                self.assertEqual(result.returncode, 9, result.stderr)
                self.assertIn("differs from approved configuration", result.stderr)
                self.assertNotIn("\nrun ", calls)
                self.assertNotIn("\nstop ", calls)

    def test_running_rollback_blocks_migration(self):
        result, calls = self.run_upgrade("previous", True, "running")
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertIn("not a stopped managed dev container", result.stderr)
        self.assertNotIn("\nstop ", calls)

    def test_failed_replacement_restores_previous_dev_and_retains_prior_rollback(self):
        result, calls = self.run_upgrade("previous", True, replacement_writable=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("restoring the previous dev", result.stderr)
        saved = next(line.split()[-1] for line in calls.splitlines()
                     if line.startswith(f"rename {DEV} "))
        self.assertIn(f"rename {saved} {DEV}", calls)
        self.assertIn(f"start {DEV}", calls)
        self.assertNotIn("rm panolab-direct-dev-1-rollback-", calls)
