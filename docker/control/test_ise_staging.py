#!/usr/bin/env python3
"""In-image tests for immutable ISE input revisions, no Docker required."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import ise_staging

ns={"__name__":"unit_stage"}
exec(compile(ise_staging.STAGE_HELPER,"ise-stage-helper","exec"),ns)
publish=ns["publish"]

class StagingContract(unittest.TestCase):
    def setUp(self):
        self._tmp=TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root=Path(self._tmp.name)
        self.src=self.root/"workspace"
        self.dst=self.root/"out"
        self.project=self.src/"ise-staging"/"smoke"
        self.project.mkdir(parents=True)
        self.dst.mkdir()
        self.manifest={"top":"demo","part":"xc6slx150-fgg484-2",
                       "verilog":["design.v"],"ucf":"design.ucf"}
        (self.project/"build.json").write_text(json.dumps(self.manifest))
        (self.project/"design.v").write_text("module demo(input clk,output led);assign led=clk;endmodule\n")
        (self.project/"design.ucf").write_text('NET "clk" LOC = "Y13";\n')
    def stage(self):
        return publish(str(self.src),str(self.dst),"smoke")
    def test_versioned_copy_and_idempotence(self):
        a=self.stage()
        self.assertTrue(a["ok"])
        self.assertEqual(self.stage()["project"],a["project"])
        self.assertTrue(self.stage()["already_staged"])
        (self.project/"design.v").write_text("module demo(input clk,output led);assign led=~clk;endmodule\n")
        b=self.stage()
        self.assertNotEqual(a["project"],b["project"])
        self.assertIn("led=clk",(self.dst/a["project"]/"design.v").read_text())
    def test_reject_symlink_and_traversal(self):
        (self.project/"design.v").unlink()
        (self.project/"design.v").symlink_to("/etc/passwd")
        with self.assertRaises(OSError):self.stage()
        with self.assertRaises(ValueError):publish(str(self.src),str(self.dst),"../bad")
    def test_reject_duplicate_keys_and_wrong_device(self):
        (self.project/"build.json").write_text('{"top":"demo","top":"dup","part":"xc6slx150-fgg484-2","verilog":["design.v"],"ucf":"design.ucf"}')
        with self.assertRaisesRegex(ValueError,"DUPLICATE_MANIFEST_KEY"):self.stage()
        self.manifest["part"]="xc6slx100-fgg484-2"
        (self.project/"build.json").write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError,"INVALID_FPGA_TARGET"):self.stage()
    def test_broker_orchestrator_mount_allowlist(self):
        import ise_proxy
        from unittest.mock import patch
        digest="b"*64
        calls=[]
        def fake_command(argv,timeout):
            calls.append(argv)
            if argv[:3]==["docker","inspect","--format"] and argv[3]=="{{json .Mounts}}":
                return {"ok":True,"stdout":json.dumps([{
                    "Type":"bind", "Destination":"/projects",
                    "Source":"/external-data/ise-work/worker/projects",
                    "RW":False}])}
            if argv[:3]==["docker","inspect","--format"] and argv[3]=="{{.Image}}":
                return {"ok":True,"stdout":"sha256:"+"a"*64}
            if argv[:2]==["docker","run"]:
                return {"ok":True,"stdout":json.dumps({
                    "ok":True,"project":"smoke-"+digest[:12],
                    "sha256":digest,"already_staged":False})}
            raise AssertionError("unexpected Docker operation")
        with patch.object(ise_proxy,"validate_worker",return_value=None):
            result=ise_staging.stage_project("smoke",fake_command,"/agent-workspace","/external-data")
        self.assertTrue(result["ok"],result)
        self.assertEqual(result["project"],"smoke-"+digest[:12])
        run=next(cmd for cmd in calls if cmd[:2]==["docker","run"])
        self.assertEqual(run[run.index("--network")+1],"none")
        self.assertIn("--read-only",run)
        self.assertIn("--cap-drop",run)
        self.assertIn("ALL",run)
        self.assertIn("--security-opt",run)
        self.assertTrue(any("src=/agent-workspace,dst=/workspace,readonly" in arg for arg in run))
        self.assertTrue(any("src=/external-data/ise-work/worker/projects,dst=/output" in arg for arg in run))
        self.assertFalse(any("docker.sock" in arg or "Xilinx.lic" in arg for arg in run))
    def test_broker_rejects_staging_into_changed_worker_mount(self):
        import ise_proxy
        from unittest.mock import patch
        def fake(argv,timeout):
            if argv[:3]==["docker","inspect","--format"]:
                return {"ok":True,"stdout":json.dumps([{
                    "Type":"bind", "Destination":"/projects","Source":"/other","RW":False}])}
            raise AssertionError("unsafe operation attempted")
        with patch.object(ise_proxy,"validate_worker",return_value=None):
            result=ise_staging.stage_project("smoke",fake,"/agent-workspace","/external-data")
        self.assertEqual(result,{"ok":False,"error":"ISE_PROJECT_MOUNT_CHANGED"})

    def test_staging_requested_project_id_is_bounded(self):
        for invalid in ("../private","bad path","x"*48):
            self.assertFalse(ise_staging.PROJECT.fullmatch(invalid))

if __name__=="__main__":
    unittest.main()
