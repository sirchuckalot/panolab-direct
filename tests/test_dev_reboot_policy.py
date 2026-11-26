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
mkdir "$root/research"
PANOLAB_WORKSPACE_HOST=/test/ws
PANOLAB_CODEX_AUTH_HOST=/test/auth
started=0
log="$(mktemp)"
trap 'rm -f "$log"; rmdir "$root/research" "$root"' EXIT
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
        *'/workspace'*)
          [[ "$CASE" == bad_workspace ]] && echo /unexpected/ws || echo /test/ws;;
        *'/codex-auth'*)
          [[ "$CASE" == bad_auth ]] && echo /unexpected/auth || echo /test/auth;;
        *'/repo/projects'*)
          [[ "$CASE" == bad_source ]] && echo /unexpected/repo || echo "$root/projects";;
        *'/repo/research'*)
          case "$CASE" in
            missing_research) ;;
            writable_research) echo "bind|$root/research|true";;
            wrong_research) echo "bind|$root/elsewhere|false";;
            *) echo "bind|$root/research|false";;
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
        beginning = '[[ -d "$root/research"'
        ending = 'current_modern_image='
        cls.snippet = source.split(beginning, 1)[1].split(ending, 1)[0]
        assert cls.snippet and ending in source
        cls.snippet = beginning + cls.snippet

    def mock_case(self, name, expect_success=True):
        script = MOCK + "\n" + self.snippet + '\necho MOCK_PASS\ncat "$log"\n'
        result = subprocess.run(
            ["bash", "-c", script],
            env={**os.environ, "CASE": name},
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

        self.assertIn("dst=/repo/research,readonly", output)
        for target in ("/repo/docker/private", "/repo/docker/.env", "/repo/.git", "dst=/repo "):
            self.assertNotIn(target, output)

    def test_existing_dev_without_research_requires_controlled_upgrade(self):
        output = self.mock_case("missing_research", expect_success=False)
        self.assertIn("panolab-install.sh --upgrade-dev", output)
        self.assertNotIn("update --restart", output)

    def test_wrong_research_mount_is_rejected(self):
        for case in ("wrong_research", "writable_research"):
            with self.subTest(case=case):
                output = self.mock_case(case, expect_success=False)
                self.assertIn("unexpected /repo/research mount", output)
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
                self.assertIn("unexpected bind mounts", output)
                self.assertNotIn("update --restart", output)


if __name__ == "__main__":
    unittest.main()
