import hashlib
import unittest
import pathlib
import tempfile
from build_identity import canonical,identity
from source_hash import source_hash

class BuildIdentityTests(unittest.TestCase):
    def test_normative_object_and_component_profile_separation(self):
        args=("1"*64,"2"*64,"3"*64,"4"*64)
        digest,obj=identity("EV3","Release",*args)
        self.assertEqual(digest,hashlib.sha256(canonical(obj)).hexdigest())
        self.assertEqual(digest,"25f628556ea1d056432fa3c36e0fd56f6b3987d390fc87e013bd847555703c16")
        self.assertEqual(obj["schema"],"PHANTOM-BUILD-V4")
        self.assertNotIn("git_commit",obj)
        self.assertNotEqual(digest,identity("QUEST","Release",*args)[0])
        self.assertNotEqual(digest,identity("EV3","Diagnostic",*args)[0])
        self.assertNotEqual(digest,identity("EV3","DeepDebug",*args)[0])

    def test_rejects_noncanonical_hex(self):
        with self.assertRaises(ValueError):identity("EV3","Release","A"*64,*(["0"*64]*3))

    def test_documentation_edits_and_removal_do_not_change_build_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory)
            (root/"protocol").mkdir()
            source=root/"protocol/runtime.py"
            document=root/"protocol/protocol.md"
            source.write_bytes(b"runtime = 1\n")
            document.write_bytes(b"old requirements\n")
            def build():
                return identity("EV3","Diagnostic",source_hash(root,["protocol"]),
                                "1"*64,"2"*64,"3"*64)[0]
            before=build()
            document.write_bytes(b"new requirements\n")
            self.assertEqual(before,build())
            document.unlink()
            self.assertEqual(before,build())
            source.write_bytes(b"runtime = 2\n")
            self.assertNotEqual(before,build())

    def test_machine_inputs_each_change_build_identity(self):
        inputs=["1"*64,"2"*64,"3"*64,"4"*64]
        before=identity("EV3","Diagnostic",*inputs)[0]
        for index in range(len(inputs)):
            changed=inputs[:];changed[index]="0"*64
            self.assertNotEqual(before,identity("EV3","Diagnostic",*changed)[0])

if __name__=="__main__":unittest.main()
