import hashlib
import unittest
from build_identity import canonical,identity

class BuildIdentityTests(unittest.TestCase):
    def test_normative_object_and_component_profile_separation(self):
        args=("0"*40,"1"*64,"2"*64,"3"*64,"4"*64,"5"*64)
        digest,obj=identity("EV3","Release",*args)
        self.assertEqual(digest,hashlib.sha256(canonical(obj)).hexdigest())
        self.assertEqual(digest,"99d59fb755f5ab34809fa9e1f832afce8d553efa29a70f7191cd831325271e82")
        self.assertNotEqual(digest,identity("QUEST","Release",*args)[0])
        self.assertNotEqual(digest,identity("EV3","Diagnostic",*args)[0])

    def test_rejects_noncanonical_hex(self):
        with self.assertRaises(ValueError):identity("EV3","Release","A"*40,*(["0"*64]*5))

if __name__=="__main__":unittest.main()
