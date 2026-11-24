#!/usr/bin/env python3
"""Build-time test of opt-in remote maintenance route without starting broker."""
import ast
from pathlib import Path
import unittest

SOURCE=Path("/usr/local/bin/panolab-broker.py")

class TrustedMaintenanceRouteTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse(SOURCE.read_text())
        fun=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="dispatch"]
        self.assertEqual(len(fun),1)
        unit=ast.Module(body=fun,type_ignores=[])
        seen=[]
        def check(_):seen.append("identity")
        def command(argv,timeout):
            seen.append((argv,timeout))
            return {"ok":True,"stdout":"trusted fixture"}
        self.context={
            "TRUSTED_MAINTENANCE":True,
            "MAINTENANCE":"panolab-direct-trusted-maintenance",
            "maintenance_identity":check,
            "command":command,
        }
        exec(compile(unit,"broker-dispatch-test","exec"),self.context)
        self.dispatch=self.context["dispatch"]
        self.seen=seen

    def test_fixed_maintenance_container_only(self):
        output=self.dispatch({"action":"exec","argv":["@maintenance","docker","ps"]})
        self.assertTrue(output["ok"])
        self.assertEqual(self.seen[0],"identity")
        self.assertEqual(self.seen[1],(
            ["docker","exec","--user","0:0","panolab-direct-trusted-maintenance","docker","ps"],170))

    def test_disabled_rejects_without_docker(self):
        self.context["TRUSTED_MAINTENANCE"]=False
        with self.assertRaisesRegex(ValueError,"disabled"):
            self.dispatch({"action":"exec","argv":["@maintenance","docker","ps"]})
        self.assertFalse(self.seen)

    def test_invalid_arguments_are_rejected(self):
        for args in (["@maintenance"],["@maintenance",""],["@maintenance","cmd","bad\x00name"],
                     ["@maintenance"]+["x"]*40):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    self.dispatch({"action":"exec","argv":args})
        self.assertFalse(self.seen)

if __name__=="__main__":
    unittest.main()
