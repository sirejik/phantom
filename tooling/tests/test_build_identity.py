import hashlib
import unittest
import pathlib
import tempfile
from build_identity import canonical,identity
from source_hash import source_hash, EV3_SOURCE_INPUTS

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
        with self.assertRaises(ValueError):identity("EV3","DeepDebug",*args)

    def test_rejects_noncanonical_hex(self):
        with self.assertRaises(ValueError):identity("EV3","Release","A"*64,*(["0"*64]*3))

    def test_documentation_edits_and_removal_do_not_change_build_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory)
            (root/"protocol").mkdir()
            (root/"docs").mkdir()
            source=root/"protocol/runtime.py"
            document=root/"docs/protocol-wire-reference.md"
            source.write_bytes(b"runtime = 1\n")
            document.write_bytes(b"old requirements\n")
            documentation_meta=root/"protocol/README.md.meta"
            documentation_meta.write_bytes(b"documentation-guid-v1\n")
            def build():
                return identity("EV3","Diagnostic",source_hash(root,["protocol", "docs"]),
                                "1"*64,"2"*64,"3"*64)[0]
            before=build()
            document.write_bytes(b"new requirements\n")
            self.assertEqual(before,build())
            documentation_meta.write_bytes(b"documentation-guid-v2\n")
            self.assertEqual(before,build())
            documentation_meta.unlink()
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

    def test_ev3_identity_ignores_tests_but_tracks_runtime_and_toolchain(self):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory)
            files={
                "ev3/src/controller_main.cpp": b"controller-v1",
                "ev3/src/network_server.cpp": b"network-v1",
                "ev3/tests/core_tests.cpp": b"test-v1",
                "ev3/tests/network_server_tests.cpp": b"network-test-v1",
                "ev3/toolchains/armel.cmake": b"flags-v1",
            }
            for name,data in files.items():
                path=root/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(data)
            before=source_hash(root,EV3_SOURCE_INPUTS)
            for name in ("ev3/tests/core_tests.cpp",
                         "ev3/tests/network_server_tests.cpp"):
                (root/name).write_bytes(b"unrelated-v2")
                self.assertEqual(before,source_hash(root,EV3_SOURCE_INPUTS),name)
            for name in ("ev3/src/controller_main.cpp", "ev3/src/network_server.cpp",
                         "ev3/toolchains/armel.cmake"):
                path=root/name
                original=path.read_bytes()
                path.write_bytes(b"runtime-v2")
                self.assertNotEqual(before,source_hash(root,EV3_SOURCE_INPUTS),name)
                path.write_bytes(original)

if __name__=="__main__":unittest.main()
