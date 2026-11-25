from dataclasses import replace
import unittest
from reconcile import Claim, Snapshot, Outcome, reconcile

class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.claim=Claim(b"i"*16,1,2,8,b"d"*32,"B")
        self.snapshot=Snapshot(b"i"*16,2,2,8,b"d"*32,"B","sealed",True,True,True,True)
    def test_verified_not_activated(self):
        self.assertEqual(reconcile(self.claim,self.snapshot),Outcome.VERIFIED_STAGED)
    def test_interrupted_even_if_image_valid(self):
        self.assertEqual(reconcile(self.claim,replace(self.snapshot,state="interrupted")),Outcome.INTERRUPTED)
    def test_cancelled(self):
        self.assertEqual(reconcile(self.claim,replace(self.snapshot,state="cancelled",candidate_verified=False)),Outcome.CANCELLED)
    def test_reject_mismatch(self):
        for fields in (dict(device_id=b"x"*16),dict(boot_epoch=1),dict(boot_epoch=0),
                       dict(operation_id=3),dict(journal_sequence=9),dict(manifest_digest=b"x"*32),
                       dict(slot="A"),dict(journal_valid=False),dict(confirmed_verified=False),
                       dict(candidate_inactive=False),dict(candidate_verified=False),dict(state="reserved"),
                       dict(state="unknown"),dict(candidate_verified=1),dict(boot_epoch=2**64)):
            with self.subTest(fields=fields):
                self.assertEqual(reconcile(self.claim,replace(self.snapshot,**fields)),Outcome.UNKNOWN)
if __name__=="__main__":unittest.main()
