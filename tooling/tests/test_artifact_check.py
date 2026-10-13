import io,pathlib,struct,tarfile,tempfile,unittest

from artifact_check import ev3_package_name, verify_ev3_archive, verify_ev3_elf


class CompilerFactTests(unittest.TestCase):
    def test_runtime_elf_architecture_and_float_abi(self):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/"runtime";header=bytearray(52)
            header[:7]=b'\x7fELF\x01\x01\x01';struct.pack_into('<H',header,18,40)
            path.write_bytes(header);verify_ev3_elf(path)
            for offset,value in ((4,2),(5,2),(18,62),(37,4)):
                bad=bytearray(header);bad[offset]=value;path.write_bytes(bad)
                with self.assertRaises(ValueError):verify_ev3_elf(path)


class ObservedCompilerTargetTests(unittest.TestCase):
    def test_target_comes_from_exported_compiler_facts(self):
        from tooling.common.environment import compiler_target
        facts = ['compiler version', 'binary hash /compiler', 'compiler_target=arm-linux-gnueabi']
        self.assertEqual(compiler_target(facts), 'arm-linux-gnueabi')
        self.assertEqual(compiler_target(' | '.join(facts)), 'arm-linux-gnueabi')
        self.assertEqual(compiler_target(['compiler_target=x86_64-linux-gnu']), 'x86_64-linux-gnu')

    def test_missing_ambiguous_and_malformed_targets_fail_closed(self):
        from tooling.common.environment import compiler_target
        from tooling.common.process import ToolError
        for facts in ([], ['compiler_target='], ['compiler_target=arbitrary label'],
                      ['compiler_target=arm-linux-gnueabi', 'compiler_target=x86_64-linux-gnu']):
            with self.assertRaises(ToolError):
                compiler_target(facts)


class PackageNameTests(unittest.TestCase):
    def test_archive_payload_must_match_validated_build_directory(self):
        required=("build-manifest.json","SHA256SUMS","bin/phantom-controller","bin/phantom-safety","bin/phantom-network","bin/phantom-mdns","bin/phantom-device-integration-test","bin/phantom-maintenance")
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory);tree=root/"tree";tree.mkdir();package=root/"build.tar.gz"
            for name in required:
                path=tree/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b"expected")
            for corrupt in (False,True):
                with tarfile.open(package,"w:gz") as archive:
                    for name in required:
                        payload=b"tampered" if corrupt and name=="bin/phantom-controller" else b"expected"
                        info=tarfile.TarInfo(name);info.size=len(payload);info.mode=0o755
                        archive.addfile(info,io.BytesIO(payload))
                if corrupt:
                    with self.assertRaisesRegex(ValueError,"archive content mismatch"):
                        verify_ev3_archive(package,tree)
                else:verify_ev3_archive(package,tree)
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
        required=("build-manifest.json","SHA256SUMS","bin/phantom-controller","bin/phantom-safety","bin/phantom-network","bin/phantom-mdns","bin/phantom-device-integration-test","bin/phantom-maintenance")
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/"bad-mode.tar.gz"
            with tarfile.open(path,"w:gz") as archive:
                for name in required:
                    info=tarfile.TarInfo(name);payload=b"x";info.size=1;info.mode=0o644
                    archive.addfile(info,io.BytesIO(payload))
            with self.assertRaisesRegex(ValueError,"not executable"):
                verify_ev3_archive(path)

    def test_legacy_python_runtime_package_is_rejected(self):
        required=("build-manifest.json","SHA256SUMS","bin/phantom-controller","bin/phantom-safety","bin/phantom-network","bin/phantom-mdns","bin/phantom-device-integration-test","bin/phantom_protocol.py","bin/jcs.py","bin/ipc_layout.py","bin/wire_schema.yaml")
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/"missing-semantics.tar.gz"
            with tarfile.open(path,"w:gz") as archive:
                for name in required:
                    info=tarfile.TarInfo(name);payload=b"x";info.size=1;info.mode=0o755
                    archive.addfile(info,io.BytesIO(payload))
            with self.assertRaisesRegex(ValueError,"must not ship Python"):
                verify_ev3_archive(path)


if __name__=="__main__":unittest.main()
