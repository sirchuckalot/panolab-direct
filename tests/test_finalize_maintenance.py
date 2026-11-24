"""Simulate exact host Buildx/rollback finalizer without accessing real Docker."""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"host/finalize-dev-maintenance.sh"
BACKUP="panolab-direct-dev-1-rollback-20261124T020818Z"

FAKE_DOCKER=r'''#!/usr/bin/env python3
import os,sys
from pathlib import Path
a=sys.argv[1:]
if a[:2]==["-H",a[1]]: a=a[2:]
state=Path(os.environ["PANOLAB_TEST_STATE"])
with (state/"docker-ops").open("a") as f:f.write(" ".join(a)+"\n")
def yes(s): print(s);sys.exit(0)
def no(): sys.exit(1)
if a[:1]==["info"]: yes('["name=rootless"]')
if a[:2]==["buildx","version"]: yes("github.com/docker/buildx v0.36.1")
if a[:3]==["buildx","inspect","default"]: yes("Name: default\nDriver: docker")
if a[:2]==["image","inspect"]: 
    if a[-1]=="panolab-direct-modern:local":
        if "{{.Id}}" in a:yes("sha256:new")
        if "org.panolab.litex.recipe" in " ".join(a):yes("modern-unified-dev-20261123-v2")
    no()
if a[:2]==["container","rm"]:
    if a[2]!=os.environ["PANOLAB_TEST_BACKUP"]: no()
    (state/"removed").write_text(a[2]);yes(a[2])
if a[:2]==["container","inspect"]:
    if a[2]==os.environ["PANOLAB_TEST_BACKUP"] and not (state/"removed").exists():yes("{}")
    no()
if a[:1]==["inspect"]:
    name=a[-1]
    expr=" ".join(a)
    if name==os.environ["PANOLAB_TEST_BACKUP"] and (state/"removed").exists():no()
    if name==os.environ["PANOLAB_TEST_BACKUP"]:
        if "{{.Name}}" in expr:yes("/"+name)
        if 'panolab.managed' in expr:yes("false" if (state/"bad-label").exists() else "true")
        if "{{.State.Running}}" in expr:yes("false")
        if "{{.Image}}" in expr:yes("sha256:old")
        if "{{.Config.WorkingDir}}" in expr:yes("/workspace")
        if 'Destination "/workspace"' in expr:yes(os.environ["PANOLAB_TEST_WORKSPACE"])
        yes("{}")
    if name=="panolab-direct-dev-1":
        if "{{.State.Running}}" in expr:yes("true")
        if "{{.Image}}" in expr:yes("sha256:new")
        if "panolab.managed" in expr:yes("true")
        if 'Destination "/workspace"' in expr:yes(os.environ["PANOLAB_TEST_WORKSPACE"])
        yes("{}")
    if name.startswith("panolab-direct-connect-"):
        if "{{.State.Running}}" in expr:yes("true")
    no()
if a[:1]==["exec"]:sys.exit(0)
no()
'''

class FinalizeHostMaintenanceTests(unittest.TestCase):
    def setUp(self):
        scratch=Path("/workspace") if Path("/workspace").is_dir() and os.access("/workspace",os.W_OK) else None
        self.temp=tempfile.TemporaryDirectory(dir=str(scratch) if scratch else None)
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)
        self.tools=self.path/"bin";self.tools.mkdir()
        fake=self.tools/"docker";fake.write_text(FAKE_DOCKER);fake.chmod(0o755)
        fakeid=self.tools/"id";fakeid.write_text(
            "#!/bin/sh\nif [ \"$1\" = -u ]; then echo 1000; exit 0; fi\nexec /usr/bin/id \"$@\"\n")
        fakeid.chmod(0o755)
        self.workspace=self.path/"workspace";self.workspace.mkdir()
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.bind(str(self.path/"docker.sock"));self.sock.listen(1)
        self.addCleanup(self.sock.close)
        self.env={**os.environ,"PATH":str(self.tools)+":"+os.environ.get("PATH",""),
          "PANOLAB_TEST_STATE":str(self.path),
          "PANOLAB_TEST_WORKSPACE":str(self.workspace),
          "PANOLAB_TEST_BACKUP":BACKUP}
        # The existing owner-local Buildx bootstrapping must be a no-op in this fixture.
    def invoke(self):
        return subprocess.run(["bash",str(SCRIPT),str(ROOT),str(self.path/"docker.sock"),
                               str(self.workspace)],env=self.env,text=True,capture_output=True)
    def test_deletes_only_expected_stopped_rollback(self):
        out=self.invoke()
        self.assertEqual(out.returncode,0,out.stderr+"\n"+out.stdout)
        self.assertEqual((self.path/"removed").read_text(),BACKUP)
        self.assertIn("SIX_SERVICE_HEALTH=PASS",out.stdout)
        actions=(self.path/"docker-ops").read_text()
        self.assertNotIn("prune",actions)
        self.assertNotIn("builder create",actions)
        self.assertNotIn("docker-container",actions)
    def test_wrong_backup_label_is_not_deleted(self):
        (self.path/"bad-label").write_text("yes")
        out=self.invoke()
        self.assertNotEqual(out.returncode,0)
        self.assertIn("Backup is not PanoLab-managed",out.stderr)
        self.assertFalse((self.path/"removed").exists())

if __name__=="__main__":
    unittest.main()
