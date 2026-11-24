"""Offline tests for scoped PanoLab GitHub push without real credentials or GitHub writes."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "docker/control/repo_gateway.py"
ASKPASS = ROOT / "docker/control/github_askpass.py"
COMPOSE = ROOT / "docker/compose.git-push.yaml"

class PushGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        content=GATEWAY.read_text()
        before,sep,_=content.partition('if not (ROOT / ".git").is_dir():')
        assert sep
        cls.api={"__name__":"test_gateway"}
        exec(compile(before,str(GATEWAY),"exec"),cls.api)

    def test_no_main_push(self):
        self.api["branch_ok"]=lambda: "main"
        self.api["origin_ok"]=lambda: None
        with self.assertRaisesRegex(ValueError,"restricted to development"):
            self.api["push"]()

    def test_push_has_exact_branch_and_askpass(self):
        self.api["branch_ok"]=lambda:"development"
        self.api["origin_ok"]=lambda:None
        calls=[]
        def fake_git(*args,**kwargs):
            calls.append((args,kwargs))
            return {"ok":True,"stdout":"","stderr":"","exit_code":0}
        self.api["git"]=fake_git
        self.assertTrue(self.api["push"]()["ok"])
        self.assertEqual(calls[-1][0],("push","origin","HEAD:refs/heads/development"))
        self.assertEqual(calls[-1][1].get("push_auth"),True)
        self.assertNotIn("--force",repr(calls))
        self.assertNotIn("refs/heads/main",repr(calls))

    def test_dirty_checkout_blocked(self):
        self.api["branch_ok"]=lambda:"development"
        self.api["origin_ok"]=lambda:None
        def dirty(*args,**kwargs):
            return {"ok":True,"stdout":" M README.md\n","stderr":""}
        self.api["git"]=dirty
        with self.assertRaisesRegex(ValueError,"clean"):
            self.api["push"]()

    def test_credentials_only_used_for_push(self):
        code=GATEWAY.read_text()
        self.assertIn('if push_auth else "/bin/false"',code)
        self.assertIn('GIT_CONFIG_GLOBAL="/dev/null"',code)
        self.assertIn('"credential.helper="',code)
        self.assertIn("origin_ok()",code)

class AskpassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location("test_askpass",str(ASKPASS))
        cls.helper=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.helper)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.secret=Path(self.temp.name)/"github-push-token"
        self.secret.write_text("github_pat_"+"A"*35+"\n")
        os.chmod(self.secret,0o600)
        self.helper.SECRET=self.secret
        self.old=sys.argv
        self.addCleanup(lambda:setattr(sys,"argv",self.old))

    def call(self,prompt):
        sys.argv=["askpass",prompt]
        output=io.BytesIO()
        old=os.write
        try:
            os.write=lambda fd,data:output.write(data)
            code=self.helper.main()
        finally:
            os.write=old
        return code,output.getvalue().decode()

    def test_username_and_password_approved_prompt(self):
        self.assertEqual(self.call("Username for 'https://github.com':"),(0,"x-access-token\n"))
        self.assertEqual(self.call("Password for 'https://x-access-token@github.com':"),(0,self.secret.read_text()))

    def test_other_hosts_denied(self):
        for prompt in ("Password for 'https://evilgithub.com':",
                       "Password for 'https://example.com':",
                       "Password for 'http://github.com':",
                       "What is the password?"):
            self.assertNotEqual(self.call(prompt)[0],0)

    def test_bad_permissions_denied(self):
        os.chmod(self.secret,0o644)
        self.assertNotEqual(self.call("Password for 'https://github.com':")[0],0)

    def test_symlink_and_classic_token_denied(self):
        other=Path(self.temp.name)/"other"
        self.secret.rename(other)
        self.secret.symlink_to(other)
        self.assertNotEqual(self.call("Password for 'https://github.com':")[0],0)
        self.secret.unlink()
        self.secret.write_text("ghp_classic_unsafe\n")
        os.chmod(self.secret,0o600)
        self.assertNotEqual(self.call("Password for 'https://github.com':")[0],0)

class ComposeAndHostContracts(unittest.TestCase):
    def test_opt_in_mount_only_repo_git(self):
        import yaml
        config=yaml.safe_load(COMPOSE.read_text())
        self.assertEqual(set(config["services"]),{"repo-git"})
        v=config["services"]["repo-git"]["volumes"][0]
        self.assertEqual(v["target"],"/run/panolab-git-auth")
        self.assertTrue(v["read_only"])
        self.assertEqual(v["bind"]["create_host_path"],False)

    def test_gateway_image_includes_git(self):
        src=(ROOT/"docker/control/Repo.Dockerfile").read_text()
        self.assertIn("apk add --no-cache git",src)
        self.assertIn("COPY github_askpass.py",src)

    def test_installer_prompts_hidden_and_does_not_run_full_system(self):
        s=(ROOT/"host/enable-github-push.sh").read_text()
        self.assertIn("read -r -s -p",s)
        self.assertIn('chmod 0600 "$tmp"',s)
        self.assertIn("up -d --no-deps --no-build --force-recreate repo-git",s)
        self.assertIn("--dry-run origin HEAD:refs/heads/development",s)
        self.assertNotIn("docker system prune",s)
        self.assertNotIn("docker compose down",s)
        launcher=(ROOT/"host/rootless-install.sh").read_text()
        self.assertIn("--enable-github-push",launcher)

if __name__=="__main__":
    unittest.main()
