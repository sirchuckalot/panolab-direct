#!/usr/bin/env python3
"""No-Docker tests for isolated, owner-approved ISE acceptance orchestration."""
import ast
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault("PANOLAB_REPO_HOST","/fixture/nonexistent-checkout")
import ise_acceptance as a

class AcceptanceContract(unittest.TestCase):
    def test_resource_names_cannot_escape_test_prefix(self):
        run="0123456789ab"
        values=a.resources(run)
        self.assertEqual(values["worker"],"panolab-ise-e2e-0123456789ab-worker")
        self.assertEqual(len(set(values.values())),8)
        self.assertTrue(all(v.startswith("panolab-ise-e2e-"+run+"-") for v in values.values()))
        for invalid in ("../dev","", "0"*64,"ABCDEF123456", "a"*11):
            with self.assertRaises(a.AcceptanceError):
                a.resources(invalid)

    def test_immutable_approved_archive_and_eula(self):
        self.assertEqual(len(a.ARCHIVE_SHA),64)
        self.assertEqual(a.ARCHIVE_SIZE,6538618880)
        self.assertEqual(a.ACCEPTANCE_CONFIRMATION,"INSTALL_ISE_14_7_IN_PANOLAB_ONLY")
        self.assertIn("unattended_terms_acceptance",a.POLICY_PROBE)
        self.assertIn("approval_scope",a.POLICY_PROBE)

    def test_setup_start_uses_separate_volumes_and_no_network(self):
        args=[]
        def fake(command,timeout=120):
            args.append(command)
            return "a"*64
        fixtures={"/media/ise.tar":"/approved/vendor.tar",
                  "/licenses/Xilinx.lic":"/approved/private.lic",
                  "/run/secrets/mcp-bearer":"/approved/mcp-token",
                  "/config/ise-system-edition.batch":"/approved/batch"}
        run=a.resources("0123456789ab");run["id"]="0123456789ab"
        with patch.object(a,"docker",fake):
            a.start_setup(run,fixtures)
        command=args[0]
        self.assertEqual(command[:2],["docker","run"])
        self.assertIn("none",command)
        self.assertIn("--read-only",command)
        self.assertIn("--cap-drop",command)
        self.assertIn("panolab.ise.acceptance=0123456789ab",command)
        self.assertTrue(any("src="+run["install"]+",dst=/opt/Xilinx" in x for x in command))
        self.assertFalse(any("src=/approved/vendor.tar,dst=/opt/Xilinx" in x for x in command))
        self.assertFalse(any("docker.sock" in x for x in command))
        self.assertFalse(any("panolab-direct-ise14-worker-1" in x for x in command))

    def test_cannot_cleanup_unmarked_resource(self):
        r=a.resources("0123456789ab");r["id"]="0123456789ab"
        called=[]
        def inspect(kind,name):
            if kind=="container" and name==r["worker"]:
                return {"Config":{"Labels":{"panolab.managed":"true",
                   "panolab.ise.acceptance":"different-run"}}}
            return None
        with patch.object(a,"try_inspect",inspect):
            with patch.object(a,"docker",lambda args,timeout=120:called.append(args)):
                with self.assertRaisesRegex(a.AcceptanceError,"CLEANUP_RESOURCE_IDENTITY_CHANGED"):
                    a.cleanup(r)
        self.assertEqual(called,[])

    def test_cleanup_names_and_order_fixed(self):
        r=a.resources("0123456789ab");r["id"]="0123456789ab"
        executed=[]
        def inspect(kind,name):
            if ("docker","rm","-f",name) in executed:
                return None
            if ("docker","network","rm",name) in executed:
                return None
            if ("docker","volume","rm",name) in executed:
                return None
            key="Config" if kind=="container" else "Labels"
            if kind=="container":return {"Config":{"Labels":{"panolab.managed":"true","panolab.ise.acceptance":r["id"]}}}
            return {"Labels":{"panolab.managed":"true","panolab.ise.acceptance":r["id"]}}
        def command(cmd,timeout=120):
            executed.append(tuple(cmd))
            return ""
        with patch.object(a,"try_inspect",inspect),patch.object(a,"docker",command):
            a.cleanup(r)
        self.assertEqual(len(executed),8)
        self.assertTrue(all(x[0]=="docker" for x in executed))
        self.assertNotIn(("docker","system","prune"),executed)

    def test_approval_policy_fail_closed(self):
        r={"id":"0123456789ab"}
        fixtures={"/media/ise.tar":"/test/media","/licenses/Xilinx.lic":"/test/license"}
        with patch.object(a,"docker_helper",return_value=json.dumps(
            {"sha":"0"*64,"bytes":6538618880,"approved":True,
             "product":"Xilinx ISE Design Suite 14.7 System Edition",
             "schema":1,"scope":True})):
            with self.assertRaisesRegex(a.AcceptanceError,"VENDOR_MEDIA_TERMS_NOT_AUTHORIZED"):
                a.pre_install_policy(r,fixtures)

    def test_status_only_returns_allowlisted_summary(self):
        record={"id":"0123456789ab","status":"passed","phase":"finished",
                "disposed":True,"bitstream_sha256":"c"*64,
                "secret":"must-not-leak","hostid":"must-not-leak"}
        with patch.object(a,"load_state",return_value=record):
            result=a.interface("result","0123456789ab")
        self.assertTrue(result["disposed"])
        self.assertNotIn("secret",result)
        self.assertNotIn("hostid",result)
        self.assertEqual(result["bitstream_sha256"],"c"*64)

    def test_acceptance_does_not_depend_on_maintenance(self):
        tree=ast.parse(Path(a.__file__).read_text())
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call)]
        self.assertFalse(any(isinstance(n.func,ast.Name) and n.func.id=="maintenance" for n in calls))
        self.assertNotIn("panolab-direct-trusted-maintenance",Path(a.__file__).read_text())
        self.assertNotIn("@maintenance",Path(a.__file__).read_text())

    def test_explicit_disposal_persists_failed_run_evidence(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(a,"RUN_ROOT",Path(temp)):
            r_id="0123456789ab"
            a.save_state({"id":r_id,"status":"failed","phase":"finished",
                         "disposed":True,"error_category":"VENDOR_FAILED"})
            result=a.interface("result",r_id)
            self.assertEqual(result["status"],"failed")
            self.assertTrue(result["disposed"])
            self.assertIn("VENDOR_FAILED",result["error_category"])

    def test_end_to_end_synthetic_success_keeps_evidence_and_disposes(self):
        ident="0123456789ab"
        with tempfile.TemporaryDirectory() as folder,patch.object(a,"RUN_ROOT",Path(folder)):
            a.save_state({"id":ident,"status":"queued","phase":"queued","disposed":False})
            called=[]
            def mock_install(r,inputs,state):
                called.append("install")
                state["archive_verified"]=True
                state["install_verified"]=True
            def mock_build(r,inputs,state):
                called.append("build")
                state["build_verified"]=True
                state["bitstream_bytes"]=4220305
                state["bitstream_sha256"]="e"*64
            with patch.object(a,"preflight",return_value={"media":"approved"}),\
                 patch.object(a,"pre_install_policy",return_value={"approved":True}),\
                 patch.object(a,"try_inspect",return_value=None),\
                 patch.object(a,"create_volumes",side_effect=lambda r:called.append("volumes")) ,\
                 patch.object(a,"run_install",side_effect=mock_install),\
                 patch.object(a,"run_build",side_effect=mock_build),\
                 patch.object(a,"cleanup",side_effect=lambda r:called.append("cleanup")):
                a.run(ident)
            outcome=a.interface("result",ident)
            self.assertEqual(called,["volumes","install","build","cleanup"])
            self.assertEqual(outcome["status"],"passed")
            self.assertTrue(outcome["disposed"])
            self.assertEqual(outcome["bitstream_bytes"],4220305)
            self.assertEqual(outcome["bitstream_sha256"],"e"*64)

    def test_end_to_end_synthetic_failure_always_disposes(self):
        ident="0123456789ab"
        with tempfile.TemporaryDirectory() as folder,patch.object(a,"RUN_ROOT",Path(folder)):
            a.save_state({"id":ident,"status":"queued","phase":"queued","disposed":False})
            removed=[]
            with patch.object(a,"preflight",return_value={"media":"approved"}),\
                 patch.object(a,"pre_install_policy",return_value={"approved":True}),\
                 patch.object(a,"try_inspect",return_value=None),\
                 patch.object(a,"create_volumes",return_value=None),\
                 patch.object(a,"run_install",side_effect=a.AcceptanceError("VENDOR_INSTALL_FAILED")),\
                 patch.object(a,"run_build",side_effect=AssertionError("Must not build")) ,\
                 patch.object(a,"cleanup",side_effect=lambda r:removed.append(r["id"])):
                a.run(ident)
            outcome=a.interface("result",ident)
            self.assertEqual(outcome["status"],"failed")
            self.assertTrue(outcome["disposed"])
            self.assertEqual(removed,[ident])
            self.assertIn("VENDOR_INSTALL_FAILED",outcome["error_category"])

    def test_cleanup_failure_is_not_reported_as_pass(self):
        ident="0123456789ab"
        with tempfile.TemporaryDirectory() as folder,patch.object(a,"RUN_ROOT",Path(folder)):
            a.save_state({"id":ident,"status":"queued","phase":"queued","disposed":False})
            with patch.object(a,"preflight",return_value={"media":"approved"}),\
                 patch.object(a,"pre_install_policy",return_value={"approved":True}),\
                 patch.object(a,"try_inspect",return_value=None),\
                 patch.object(a,"create_volumes",return_value=None),\
                 patch.object(a,"run_install",return_value=None),\
                 patch.object(a,"run_build",return_value=None),\
                 patch.object(a,"cleanup",side_effect=a.AcceptanceError("DISPOSAL_RESOURCE_REMAINS")):
                a.run(ident)
            outcome=a.interface("result",ident)
            self.assertEqual(outcome["status"],"cleanup_failed")
            self.assertFalse(outcome["disposed"])

    def test_named_images_are_checkpointed_not_current_mutable_local(self):
        self.assertEqual(a.SETUP_IMAGE,"panolab-direct-ise14-setup:checkpoint-20261124")
        self.assertEqual(a.WORKER_IMAGE,"panolab-direct-ise14-worker:checkpoint-20261124")
        self.assertNotEqual(a.SETUP_ORIGINAL,a.resources("0123456789ab")["setup"])
        self.assertNotEqual(a.WORKER_ORIGINAL,a.resources("0123456789ab")["worker"])

if __name__=="__main__":
    unittest.main()
