#!/usr/bin/env python3
"""Test safe Git reconciliation using disposable bare repositories. No Docker."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/"host/reconcile-and-upgrade.sh"

def run(cwd,*args,env=None,check=True):
    return subprocess.run(args,cwd=cwd,env=env,text=True,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=check)

class ReconcileTests(unittest.TestCase):
    def setUp(self):
        # The rootless development container mounts /tmp noexec, while
        # /workspace is its owned executable scratch volume. On a host,
        # ordinary tempfile policy applies instead.
        scratch = Path("/workspace") if Path("/workspace").is_dir() and os.access("/workspace", os.W_OK) else None
        self.tmp=tempfile.TemporaryDirectory(dir=str(scratch) if scratch else None)
        self.addCleanup(self.tmp.cleanup)
        self.d=Path(self.tmp.name)
        self.remote=self.d/"origin.git"
        self.seed=self.d/"seed"
        self.local=self.d/"local"
        self.fake=self.d/"fakebin"
        self.fake.mkdir()
        self.env={**os.environ,"GIT_AUTHOR_NAME":"PanoLab Test",
            "GIT_AUTHOR_EMAIL":"test@example.invalid",
            "GIT_COMMITTER_NAME":"PanoLab Test",
            "GIT_COMMITTER_EMAIL":"test@example.invalid",
            "GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null"}
        run(self.d,"git","init","--bare",str(self.remote),env=self.env)
        run(self.d,"git","init","-b","main",str(self.seed),env=self.env)
        (self.seed/"README.md").write_text("old\n")
        (self.seed/"panolab-install.sh").write_text("#!/usr/bin/env bash\necho MOCK_DEV_UPGRADE_OK\n")
        run(self.seed,"git","add",".",env=self.env)
        run(self.seed,"git","commit","-m","base",env=self.env)
        run(self.seed,"git","remote","add","origin",str(self.remote),env=self.env)
        run(self.seed,"git","push","origin","main",env=self.env)
        run(self.d,"git","--git-dir",str(self.remote),"symbolic-ref","HEAD","refs/heads/main",env=self.env)
        run(self.d,"git","clone","--quiet",str(self.remote),str(self.local),env=self.env)
        run(self.local,"git","switch","-c","development",env=self.env)
        run(self.seed,"git","switch","-c","development",env=self.env)
        (self.seed/"README.md").write_text("reference tree\n")
        run(self.seed,"git","add","README.md",env=self.env)
        run(self.seed,"git","commit","-m","remote milestone",env=self.env)
        self.reference=run(self.seed,"git","rev-parse","HEAD",env=self.env).stdout.strip()
        (self.seed/"docs.txt").write_text("new product work\n")
        run(self.seed,"git","add","docs.txt",env=self.env)
        run(self.seed,"git","commit","-m","remote follow-up",env=self.env)
        self.target=run(self.seed,"git","rev-parse","HEAD",env=self.env).stdout.strip()
        run(self.seed,"git","push","origin","development",env=self.env)
        (self.fake/"git").write_text(
            '#!/bin/sh\nif [ "$1" = remote ] && [ "$2" = get-url ] && [ "$3" = origin ]; then\n'
            'echo https://github.com/sirchuckalot/panolab-direct; exit 0; fi\n'
            'exec /usr/bin/git "$@"\n')
        (self.fake/"id").write_text(
            '#!/bin/sh\nif [ "$1" = -u ]; then echo 1000; exit 0; fi\n'
            'exec /usr/bin/id "$@"\n')
        for f in self.fake.iterdir(): f.chmod(0o755)
        self.env["PATH"]=str(self.fake)+":"+self.env.get("PATH","")
        self.env["PANOLAB_EXPECTED_DEV_SHA"]=self.target

    def bridge(self):
        old=run(self.local,"git","rev-parse","HEAD",env=self.env).stdout.strip()
        text=SCRIPT.read_text().replace("f1ca3a66e48aa9fc5acf4827d0bcb779143aae51",old)
        text=text.replace("863715050d1894320590b47a3607543f1cf0a8eb",self.reference)
        testfile=self.d/"fixture.sh"
        testfile.write_text(text)
        run(self.local,"git","fetch","origin","development",env=self.env)
        r=run(self.local,"bash",str(testfile),env=self.env,check=False)
        return r,old

    def create_local(self,content):
        (self.local/"README.md").write_text(content)
        run(self.local,"git","add","README.md",env=self.env)
        run(self.local,"git","commit","-m","local parallel history",env=self.env)

    def test_equivalent_tree_preserved_and_advanced(self):
        self.create_local("reference tree\n")
        r,old=self.bridge()
        self.assertEqual(r.returncode,0,(r.stdout,r.stderr))
        self.assertIn("MOCK_DEV_UPGRADE_OK",r.stdout)
        self.assertEqual(run(self.local,"git","rev-parse","HEAD",env=self.env).stdout.strip(),self.target)
        self.assertEqual(run(self.local,"git","rev-parse","panolab/backup-development-f1ca3a66",env=self.env).stdout.strip(),old)

    def test_different_tree_rejected_unchanged(self):
        self.create_local("unexpected local content\n")
        r,old=self.bridge()
        self.assertNotEqual(r.returncode,0)
        self.assertIn("refusing reconciliation",r.stderr)
        self.assertEqual(run(self.local,"git","rev-parse","HEAD",env=self.env).stdout.strip(),old)

    def test_dirty_worktree_rejected_unchanged(self):
        self.create_local("reference tree\n")
        (self.local/"untracked.txt").write_text("keep\n")
        r,old=self.bridge()
        self.assertNotEqual(r.returncode,0)
        self.assertIn("Local source changes exist",r.stderr)
        self.assertEqual(run(self.local,"git","rev-parse","HEAD",env=self.env).stdout.strip(),old)

if __name__=="__main__":
    unittest.main()
