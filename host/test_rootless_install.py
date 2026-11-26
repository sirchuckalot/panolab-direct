"""Execute the installer's embedded image check with a synthetic toolchain."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


class RootlessInstallTests(unittest.TestCase):
    def test_litex_bootstrap_receives_all_arguments_in_one_invocation(self):
        installer = Path(__file__).with_name("rootless-install.sh").read_text()
        script = re.search(
            r"--entrypoint /bin/sh panolab-direct-modern:local -ec\s+\\\s+'([^']+)'",
            installer,
        ).group(1)
        with tempfile.TemporaryDirectory() as directory:
            tools = Path(directory)
            # Stub availability checks without requiring executable temp files.
            script = 'command() { [ "$1" = -v ]; }\n' + script
            script = script.replace("/opt/panolab", str(tools))
            script = re.sub(r"/usr/local/bin/codex(?:-code-mode-host)?", "/bin/sh", script)
            (tools / "litex").mkdir()
            (tools / "litex/env.sh").write_text("fixture")
            (tools / "recipes").mkdir()
            (tools / "recipes/litex-bootstrap.py").write_text(
                "import json, sys\nprint(json.dumps(sys.argv[1:]))\n"
            )
            result = subprocess.run(
                ["/bin/sh", "-ec", script], capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout.splitlines()[-1]), [
                "--prefix", str(tools / "litex"),
                "--lock", str(tools / "recipes/litex-upstream.lock.json"),
                "--requirements", str(tools / "recipes/litex-requirements.txt"),
                "--verify-only",
            ])
