"""Standalone rootless development container reboot/startup contract.

Runs with mocked Docker calls: no daemon, credentials or FPGA required.
"""
from pathlib import Path
import os
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = Path(os.environ.get(
    "PANOLAB_INSTALLER_UNDER_TEST", ROOT / "host/rootless-install.sh"
))

MOCK = r"""set -euo pipefail
dev=panolab-direct-dev-1
root="$(mktemp -d)"
mkdir -p "$root/docker/control"
cp "$MOCK_SOURCE" "$root/docker/control/dev_source.py"
PANOLAB_WORKSPACE_HOST=/test/ws
PANOLAB_CODEX_AUTH_HOST=/test/auth
started=0
log="$(mktemp)"
trap 'rm -f "$log"; rm -rf "$root"' EXIT
fail() { echo "BLOCKED: $*" >&2; exit 9; }
say() { :; }
new_exists() { [[ "$CASE" != fresh ]]; }
running_new() {
  [[ "$CASE" == fresh || "$CASE" == existing_running ||
     "$CASE" == existing_correct || "$started" -eq 1 ]]
}
r() {
  case "$1" in
    inspect)
      case "$3" in
        *'.Mounts'*)
          case "$CASE" in
            bad_workspace|bad_auth|bad_source|missing_research|writable_research|wrong_research)
              echo '[] {}';;
            *)
              printf '[{"Type":"bind","Source":"%s","Destination":"/repo","RW":false},{"Type":"bind","Source":"/test/ws","Destination":"/workspace","RW":true},{"Type":"bind","Source":"/test/auth","Destination":"/codex-auth","RW":true}] {"/tmp":"","/home":"","/repo/.git":"ro,nosuid,nodev,noexec,size=64k"}\n' "$root";;
          esac;;
        *'RestartPolicy.Name'*)
          [[ "$CASE" == existing_correct ]] && echo unless-stopped || echo no;;
        *'.Image'*)
          echo sha256:example-id;;
        *) echo "mock inspect unsupported: $*" >&2; return 4;;
      esac;;
    image)
      [[ "$2" == inspect ]] && { echo sha256:example-id; return 0; }
      echo "unrecognized image call: $*" >&2; return 4;;
    run|update)
      printf '%s\n' "$*" >> "$log";;
    start)
      started=1
      printf '%s\n' "$*" >> "$log";;
    *) echo "unexpected mock Docker call: $*" >&2; return 4;;
  esac
}
"""


class RestartPolicyContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = INSTALLER.read_text()
        beginning = 'if ! new_exists "$dev"; then'
        ending = 'current_modern_image='
        cls.snippet = source.split(beginning, 1)[1].split(ending, 1)[0]
        assert cls.snippet and ending in source
        cls.snippet = beginning + cls.snippet

    def mock_case(self, name, expect_success=True):
        script = MOCK + "\n" + self.snippet + '\necho MOCK_PASS\ncat "$log"\n'
        result = subprocess.run(
            ["bash", "-c", script],
            env={**os.environ, "CASE": name, "MOCK_SOURCE": str(ROOT / "docker/control/dev_source.py")},
            capture_output=True, text=True, check=False,
        )
        if expect_success:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("MOCK_PASS", result.stdout)
        else:
            self.assertEqual(result.returncode, 9, result.stderr)
            self.assertNotIn("MOCK_PASS", result.stdout)
        return result.stdout + "\n" + result.stderr

    def test_new_container_has_restart_policy(self):
        output = self.mock_case("fresh")
        self.assertIn("run -d --name panolab-direct-dev-1 --restart unless-stopped", output)

        self.assertIn("dst=/repo,readonly", output)
        self.assertIn("--tmpfs /repo/.git:ro,nosuid,nodev,noexec,size=64k", output)
        for target in ("/repo/docker/private", "/repo/docker/.env", "dst=/repo "):
            self.assertNotIn(target, output)

    def test_existing_dev_without_research_requires_controlled_upgrade(self):
        output = self.mock_case("missing_research", expect_success=False)
        self.assertIn("Use the guarded upgrade", output)
        self.assertNotIn("update --restart", output)

    def test_wrong_research_mount_is_rejected(self):
        for case in ("wrong_research", "writable_research"):
            with self.subTest(case=case):
                output = self.mock_case(case, expect_success=False)
                self.assertIn("differs from the approved root mount", output)
                self.assertNotIn("update --restart", output)

    def test_legacy_running_container_policy_repaired(self):
        output = self.mock_case("existing_running")
        self.assertIn("update --restart unless-stopped panolab-direct-dev-1", output)
        self.assertNotIn("start panolab-direct-dev-1", output)

    def test_legacy_stopped_container_policy_and_start_repaired(self):
        output = self.mock_case("existing_stopped")
        self.assertIn("update --restart unless-stopped panolab-direct-dev-1", output)
        self.assertIn("start panolab-direct-dev-1", output)

    def test_correct_existing_policy_not_rewritten(self):
        output = self.mock_case("existing_correct")
        self.assertNotIn("update --restart", output)
        self.assertNotIn("start panolab-direct-dev-1", output)

    def test_unexpected_mounts_fail_closed(self):
        for name in ("bad_workspace", "bad_auth", "bad_source"):
            with self.subTest(mount=name):
                output = self.mock_case(name, expect_success=False)
                self.assertIn("differs from the approved root mount", output)
                self.assertNotIn("update --restart", output)


if __name__ == "__main__":
    unittest.main()
