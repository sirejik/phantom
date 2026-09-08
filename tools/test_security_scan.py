#!/usr/bin/env python3
"""The provisioning audit must actually detect the material it claims to."""
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("phantom_security_scan", str(ROOT / "tools" / "security_scan.py"))
SCAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCAN)


class DetectionTests(unittest.TestCase):
    def scan(self, contents, name="candidate.txt"):
        findings = []
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / name
            path.write_bytes(contents)
            SCAN.scan_bytes(name, contents, findings, path)
        return findings

    def test_pem_private_key(self):
        self.assertTrue(self.scan(b"-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n"))

    def test_labelled_psk_hex(self):
        self.assertTrue(self.scan(b'control_psk = "' + b"ab" * 32 + b'"'))

    def test_wifi_passphrase_literal(self):
        self.assertTrue(self.scan(b'Passphrase = "correct-horse-battery"'))

    def test_keystore_password_literal(self):
        self.assertTrue(self.scan(b'keystorePass: "hunter2xyz"'))

    def test_bearer_token_literal(self):
        self.assertTrue(self.scan(b'api_token = "abcdefghijklmnopqrstuvwxyz012345"'))

    def test_raw_32_byte_high_entropy_blob(self):
        blob = bytes((i * 7 + 13) % 256 for i in range(32))
        self.assertTrue(self.scan(blob, "control.psk"))

    def test_raw_blob_in_a_text_file_is_not_flagged(self):
        # Source files legitimately contain 32-byte constants.
        blob = bytes(range(32))
        self.assertFalse(self.scan(blob, "vectors.py"))

    def test_code_assignment_from_an_api_property_is_not_a_secret(self):
        self.assertFalse(self.scan(b"var oldKeystorePass=PlayerSettings.Android.keystorePass;"))

    def test_public_key_identifier_is_not_a_secret(self):
        self.assertFalse(self.scan(b'"control_key_id":"phantom01-control"'))


class JsonArtifactTests(unittest.TestCase):
    def scan_document(self, document):
        findings = []
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "artifact.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            SCAN.scan_json_artifact("artifact.json", path, findings)
        return findings

    def test_declared_hash_fields_are_accepted(self):
        self.assertFalse(self.scan_document({"artifact_hashes": {"ev3": "ab" * 32},
                                             "specification_sha256": "cd" * 32,
                                             "build_id": "ef" * 32}))

    def test_undeclared_64_hex_value_is_flagged(self):
        self.assertTrue(self.scan_document({"network": {"shared_value": "ab" * 32}}))

    def test_base64_key_material_is_flagged(self):
        import base64
        blob = base64.b64encode(bytes((i * 11 + 5) % 256 for i in range(32))).decode("ascii")
        self.assertTrue(self.scan_document({"provisioning": {"blob": blob}}))

    def test_public_key_identifier_field_is_skipped(self):
        self.assertFalse(self.scan_document({"network": {"control_key_id": "ab" * 32}}))

    def test_legacy_device_report_hash_detail_is_narrowly_allowed(self):
        digest = "ab" * 32
        self.assertFalse(self.scan_document({"test_id": "installed-config-hash", "detail": digest}))
        self.assertFalse(self.scan_document({"test_id": "installed-bundle-hash", "detail": digest}))
        self.assertTrue(self.scan_document({"test_id": "unrelated-check", "detail": digest}))


class PolicyTests(unittest.TestCase):
    def test_test_directories_are_no_longer_blanket_exempt(self):
        source = (ROOT / "tools" / "security_scan.py").read_text(encoding="utf-8")
        self.assertNotIn('"/test" in rel', source)
        self.assertNotIn('"/test" in relative', source)

    def test_this_fixture_file_is_allowlisted_by_name(self):
        # It contains deliberate credential-shaped strings so the detectors are
        # provably wired. It is exempt by exact path with a stated reason, never
        # because it happens to live under a test directory.
        self.assertIn("tools/test_security_scan.py", SCAN.FIXTURE_ALLOWLIST)

    def test_allowlist_is_explicit_and_justified(self):
        self.assertTrue(SCAN.FIXTURE_ALLOWLIST)
        for path, reason in SCAN.FIXTURE_ALLOWLIST.items():
            self.assertTrue((ROOT / path).is_file(), path)
            self.assertGreater(len(reason), 20, path)

    def test_findings_never_echo_the_secret(self):
        secret = b"ab" * 32
        findings = []
        SCAN.scan_bytes("x", b'control_psk = "' + secret + b'"', findings)
        self.assertTrue(findings)
        for finding in findings:
            self.assertNotIn(secret.decode("ascii"), finding)


if __name__ == "__main__":
    unittest.main()
