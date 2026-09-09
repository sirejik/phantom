import io,pathlib,tarfile,tempfile,unittest

from artifact_check import compiler_matches, ev3_package_name, verify_ev3_archive


class CompilerFactTests(unittest.TestCase):
    def test_debian_version_parentheses_match_compact_lock(self):
        facts="arm-linux-gnueabi-g++ (Debian 6.3.0-18) 6.3.0 20170516 | abc  /usr/bin/arm-linux-gnueabi-g++"
        self.assertTrue(compiler_matches("arm-linux-gnueabi-g++ 6.3.0-18",facts))

    def test_wrong_executable_or_package_revision_rejected(self):
        facts="arm-linux-gnueabi-g++ (Debian 6.3.0-17) 6.3.0 20170516"
        self.assertFalse(compiler_matches("arm-linux-gnueabi-g++ 6.3.0-18",facts))
        self.assertFalse(compiler_matches("arm-linux-gnueabihf-g++ 6.3.0-17",facts))


class PackageNameTests(unittest.TestCase):
    def test_content_addressed_package_name(self):
        self.assertEqual(ev3_package_name("abc"),"phantom-abc.tar.gz")

    def test_archive_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/"unsafe.tar.gz"
            with tarfile.open(path,"w:gz") as archive:
                info=tarfile.TarInfo("../escape");payload=b"x";info.size=len(payload)
                archive.addfile(info,io.BytesIO(payload))
            with self.assertRaisesRegex(ValueError,"unsafe EV3 archive path"):
                verify_ev3_archive(path)

    def test_archive_root_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/"root-member.tar.gz"
            with tarfile.open(path,"w:gz") as archive:
                info=tarfile.TarInfo(".");info.type=tarfile.DIRTYPE
                archive.addfile(info)
            with self.assertRaisesRegex(ValueError,r"unsafe EV3 archive path: \."):
                verify_ev3_archive(path)

    def test_required_executable_mode_is_checked(self):
        required=("build-manifest.json","SHA256SUMS","bin/phantom-controller","bin/phantom-safety","bin/phantom-network","bin/phantom-mdns","bin/phantom-device-integration-test","bin/phantom_protocol.py","bin/jcs.py","bin/ipc_layout.py","bin/wire_schema.yaml","bin/semantics.yaml")
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/"bad-mode.tar.gz"
            with tarfile.open(path,"w:gz") as archive:
                for name in required:
                    info=tarfile.TarInfo(name);payload=b"x";info.size=1;info.mode=0o644
                    archive.addfile(info,io.BytesIO(payload))
            with self.assertRaisesRegex(ValueError,"not executable"):
                verify_ev3_archive(path)

    def test_protocol_semantics_runtime_input_is_required(self):
        required=("build-manifest.json","SHA256SUMS","bin/phantom-controller","bin/phantom-safety","bin/phantom-network","bin/phantom-mdns","bin/phantom-device-integration-test","bin/phantom_protocol.py","bin/jcs.py","bin/ipc_layout.py","bin/wire_schema.yaml")
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/"missing-semantics.tar.gz"
            with tarfile.open(path,"w:gz") as archive:
                for name in required:
                    info=tarfile.TarInfo(name);payload=b"x";info.size=1;info.mode=0o755
                    archive.addfile(info,io.BytesIO(payload))
            with self.assertRaisesRegex(ValueError,"inventory is incomplete"):
                verify_ev3_archive(path)


if __name__=="__main__":unittest.main()
