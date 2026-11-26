#!/usr/bin/env python3
"""Unprivileged, no-Docker tests for the ordinary setup broker bridge."""
import ast
import json
import unittest
from pathlib import Path
import ise_setup

class SetupProbeContract(unittest.TestCase):
    def command(self,args,timeout):
        if args[:3]==["docker","inspect","--format"]:
            return {"ok":True,"stdout":"/"+ise_setup.SETUP+"|true|panolab-direct-external|false"}
        if args[:3]==["docker","exec","--user"]:
            name=args[-1]
            if name=="info":
                data={"tarball":True,"license":True,"installed":True,"docker_socket":False}
            elif name=="status":
                data={"state":"succeeded","error":""}
            elif name=="inspect":
                data={"sha256":"a"*64,"bytes":153200,"license":True}
            elif name=="reject_invalid_install":
                return {"ok":False,"stdout":json.dumps({"ok":False,"category":"REJECTED"})}
            else:raise AssertionError("Unexpected normal setup action")
            return {"ok":True,"stdout":json.dumps({"ok":True,"fields":data})}
        raise AssertionError("Unexpected Docker invocation")

    def test_installed_info(self):
        data=ise_setup.call_setup({"operation":"info"},self.command)
        self.assertEqual(data,{"ok":True,"operation":"info","available":True,"tarball":True,
           "license":True,"installed":True,"docker_socket":False})

    def test_install_state(self):
        data=ise_setup.call_setup({"operation":"status"},self.command)
        self.assertEqual(data["install_state"],"succeeded")

    def test_media_integrity_summary(self):
        data=ise_setup.call_setup({"operation":"inspect"},self.command)
        self.assertEqual(data["archive_sha256"],"a"*64)
        self.assertEqual(data["archive_bytes"],153200)

    def test_invalid_install_does_not_start(self):
        data=ise_setup.call_setup({"operation":"reject_invalid_install"},self.command)
        self.assertTrue(data["rejected_without_install"])

    def test_stopped_setup(self):
        def stopped(a,t):
            result=self.command(a,t)
            if a[:3]==["docker","inspect","--format"]:
                result["stdout"]=result["stdout"].replace("|true|","|false|",1)
            return result
        self.assertEqual(ise_setup.call_setup({"operation":"status"},stopped),
          {"ok":True,"operation":"status","available":False,"state":"stopped"})

    def test_missing_setup(self):
        def missing(a,t):
            self.assertEqual(a[:3],["docker","inspect","--format"])
            return {"ok":False,"stdout":""}
        self.assertEqual(ise_setup.call_setup({"operation":"info"},missing)["state"],"not_created")

    def test_reject_unscoped_action(self):
        def unreachable(a,t):raise AssertionError("Must not execute Docker")
        for action in ("install","install_start","exec","recreate","shell","__dict__",None):
            with self.subTest(action=action):
                self.assertEqual(ise_setup.call_setup({"operation":action},unreachable),
                 {"ok":False,"error":"SETUP_OPERATION_NOT_ALLOWED"})

    def test_refuse_insecure_setup_identity(self):
        def bad(a,t):
            result=self.command(a,t)
            if a[:3]==["docker","inspect","--format"]:
                result["stdout"]=result["stdout"].replace("|false","|true")
            return result
        self.assertEqual(ise_setup.call_setup({"operation":"info"},bad)["error"],"SETUP_IDENTITY_CHANGED")

    def test_broker_dispatch_uses_normal_setup_route(self):
        import sys
        original=Path(__file__).with_name("broker.py")
        if not original.is_file():
            original=Path("/usr/local/bin/panolab-broker.py")
        tree=ast.parse(original.read_text())
        dispatch=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="dispatch")
        callback=compile(ast.Module(body=[dispatch],type_ignores=[]),
                         str(original),"exec")
        calls=[]
        class FakeSetup:
            @staticmethod
            def call_setup(request,command):
                calls.append(request)
                return {"ok":True,"operation":request["operation"]}
        ns={"ise_setup":FakeSetup,"TRUSTED_MAINTENANCE":False,
            "command":lambda *args:None}
        exec(callback,ns)
        for operation in ("info","status","inspect","reject_invalid_install"):
            result=ns["dispatch"]({"action":"exec","argv":["@setup",operation]})
            self.assertTrue(result["ok"])
            self.assertEqual(result["operation"],operation)
        self.assertEqual(len(calls),4)
        self.assertFalse(any("install_start"==x["operation"] for x in calls))

    def test_embedded_client_excludes_real_install_confirmation(self):
        self.assertNotIn("INSTALL_ISE_14_7_IN_PANOLAB_ONLY",ise_setup.PROBE)
        self.assertIn("INTENTIONALLY_INVALID",ise_setup.PROBE)
        self.assertIn("http://manager:8767/mcp",ise_setup.PROBE)
        self.assertNotIn("@maintenance",ise_setup.PROBE)

if __name__=="__main__":unittest.main()
