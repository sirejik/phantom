import hashlib
import unittest
from build_identity import canonical,identity

class BuildIdentityTests(unittest.TestCase):
    def test_normative_object_and_component_profile_separation(self):
        args=("1"*64,"2"*64,"3"*64,"4"*64,"5"*64)
        digest,obj=identity("EV3","Release",*args)
        self.assertEqual(digest,hashlib.sha256(canonical(obj)).hexdigest())
        self.assertEqual(digest,"15875ab21bca01af973de23f93a9f9ff814c8a1131e2980240325c63cd60f2a4")
        self.assertEqual(obj["schema"],"PHANTOM-BUILD-V2")
        self.assertNotIn("git_commit",obj)
        self.assertNotEqual(digest,identity("QUEST","Release",*args)[0])
        self.assertNotEqual(digest,identity("EV3","Diagnostic",*args)[0])
        self.assertNotEqual(digest,identity("EV3","DeepDebug",*args)[0])

    def test_rejects_noncanonical_hex(self):
        with self.assertRaises(ValueError):identity("EV3","Release","A"*64,*(["0"*64]*4))

if __name__=="__main__":unittest.main()
