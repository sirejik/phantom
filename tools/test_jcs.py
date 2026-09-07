#!/usr/bin/env python3
"""RFC 8785 conformance for the shared PHANTOM canonicalizer."""
import hashlib
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "protocol"))
import jcs  # noqa: E402


class NumberSerializationTests(unittest.TestCase):
    def test_ecmascript_number_to_string(self):
        # Each of these differs from repr()/json.dumps() in at least one form.
        cases = [
            (0, "0"), (-0.0, "0"), (0.0, "0"), (1, "1"), (-1, "-1"),
            (1.0, "1"), (2.0, "2"), (100.0, "100"), (0.5, "0.5"), (0.1, "0.1"),
            (-1.25, "-1.25"), (1e20, "100000000000000000000"), (1e21, "1e+21"),
            (1e-6, "0.000001"), (1e-7, "1e-7"), (1.5e-9, "1.5e-9"),
            (9.999999999999997e22, "9.999999999999997e+22"),
            (333333333.33333331, "333333333.3333333"),
            (9007199254740991, "9007199254740991"),
        ]
        for value, expected in cases:
            self.assertEqual(expected, jcs.serialize_number(value), repr(value))

    def test_python_repr_would_differ(self):
        # Guards the reason this module exists: json.dumps is not JCS.
        self.assertNotEqual(json.dumps(1.0), jcs.serialize_number(1.0))
        self.assertNotEqual(json.dumps(1e-6), jcs.serialize_number(1e-6))
        self.assertNotEqual(json.dumps(1e20), jcs.serialize_number(1e20))

    def test_non_finite_and_out_of_range_fail_closed(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            self.assertRaises(jcs.CanonicalizationError, jcs.serialize_number, bad)
        self.assertRaises(jcs.CanonicalizationError, jcs.serialize_number, 2 ** 63)
        self.assertRaises(jcs.CanonicalizationError, jcs.serialize_number, True)


class OrderingTests(unittest.TestCase):
    def test_members_sort_by_utf16_code_unit(self):
        value = {"é": 1, "\U0001f600": 2, "פּ": 3, "a": 4}
        # UTF-16 puts the surrogate pair (0xD83D) below U+FB44; a code point sort
        # would place U+1F600 last.
        self.assertEqual(b'{"a":4,"\xc3\xa9":1,"\xf0\x9f\x98\x80":2,"\xef\xad\x84":3}',
                         jcs.canonicalize(value))
        self.assertNotEqual(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            jcs.canonicalize(value))

    def test_arrays_keep_document_order(self):
        self.assertEqual(b"[3,1,2]", jcs.canonicalize([3, 1, 2]))


class DocumentTests(unittest.TestCase):
    def test_literals_strings_and_nesting(self):
        self.assertEqual(b"{}", jcs.canonicalize({}))
        self.assertEqual(b"[]", jcs.canonicalize([]))
        self.assertEqual(b'{"f":false,"n":null,"t":true}',
                         jcs.canonicalize({"t": True, "n": None, "f": False}))
        self.assertEqual(b'{"s":"a\\nb\\"c\\\\d\\te"}',
                         jcs.canonicalize({"s": "a\nb\"c\\d\te"}))

    def test_unsupported_types_fail_closed(self):
        self.assertRaises(jcs.CanonicalizationError, jcs.canonicalize, {1: "int key"})
        self.assertRaises(jcs.CanonicalizationError, jcs.canonicalize, {"x": object()})


class GoldenVectorTests(unittest.TestCase):
    def test_generated_vectors_match(self):
        vectors = json.loads((ROOT / "protocol" / "golden_vectors" / "jcs_v1.json").read_text(encoding="utf-8"))
        self.assertEqual("RFC 8785", vectors["specification"])
        self.assertTrue(vectors["vectors"])
        for vector in vectors["vectors"]:
            value = json.loads(vector["input_json"])
            encoded = jcs.canonicalize(value)
            self.assertEqual(vector["canonical_utf8_hex"], encoded.hex(), vector["name"])
            self.assertEqual(vector["sha256"], hashlib.sha256(encoded).hexdigest(), vector["name"])


class ShippedArtifactStabilityTests(unittest.TestCase):
    def test_current_artifacts_are_already_canonical(self):
        # The migration to JCS must not silently move any existing identity.
        for path in sorted((ROOT / "config" / "generated").glob("*.json")):
            raw = path.read_bytes()
            self.assertEqual(raw, jcs.canonicalize(json.loads(raw.decode("utf-8"))) + b"\n", str(path))


if __name__ == "__main__":
    unittest.main()
