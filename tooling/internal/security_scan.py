#!/usr/bin/env python3
"""Release provisioning audit: no credential material in anything we ship.

The previous scanner matched two regular expressions and skipped every path
containing `/test`, which made "secret scan PASS" much weaker than the audit
TEST_PLAN describes. This version inspects repository content, generated
configuration, build manifests, the CommissioningBundle, packaged artifacts and
APK entries, and it only exempts an explicit, narrow allowlist of synthetic
fixtures instead of a whole directory pattern.
"""
import argparse
import base64
import json
import math
import pathlib
import re
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]

# Deliberately synthetic, non-secret fixtures. Each entry is a specific path plus
# the reason it can never be production credential material.
FIXTURE_ALLOWLIST = {
    "protocol/golden_vectors/v1.json": "deterministic wire vectors keyed with the published test key bytes(range(32))",
    "protocol/golden_vectors/ipc_v1.json": "deterministic IPC layout vectors, no key material",
    "protocol/golden_vectors/jcs_v1.json": "RFC 8785 canonicalization vectors, no key material",
    "tooling/tests/test_security_scan.py": "self-test fixtures that must look like credentials so the detectors are provably wired; every literal here is invented in-file and matches nothing deployable",
}

# Directories whose content is local capture, never shipped.
SKIPPED_PREFIXES = (".secrets/", ".ev3-ssh/", "results/ev3/raw/")

# A credential leak is a *literal* value in a shipped file. Assignments whose
# right-hand side is another identifier or an API property are code, not secrets,
# so every value pattern below requires a quoted literal.
PATTERNS = [
    ("pem_private_key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("labelled_psk_hex", re.compile(rb"(?i)(?:control|commissioning)[_-]?(?:psk|secret|key)\s*[:=]\s*['\"]?[0-9a-fA-F]{64}")),
    ("wifi_passphrase", re.compile(rb"(?i)(?:passphrase|wpa[_-]?psk|wifi[_-]?password)\s*[:=]\s*['\"][^'\"\n]{8,}['\"]")),
    ("keystore_password", re.compile(rb"(?i)(?:keystore|keyalias|signing)[_-]?(?:pass|password|pwd)\s*[:=]\s*['\"][^'\"\n]{4,}['\"]")),
    ("bearer_or_api_token", re.compile(rb"(?i)(?:secret[_-]?access[_-]?key|api[_-]?token|bearer)\s*[:=]\s*['\"][A-Za-z0-9/+_.-]{20,}['\"]")),
    ("private_key_blob", re.compile(rb"(?i)\"private_key\"\s*:\s*\"[A-Za-z0-9/+=]{40,}")),
]

# Any path segment naming a digest or identifier makes a 64-hex value expected.
HASH_TRAIL_MARKERS = ("hash", "sha256", "digest", "id", "checksum", "manifest")

# Keys whose *identifier* is public by design; only their value would be secret.
PUBLIC_KEY_ID_FIELDS = ("control_key_id", "commissioning_key_id", "signing_key_id", "key_slot")

# Legacy DEVICE AUTO reports emitted these public digests as the entire detail
# value before the runner gained structured evidence fields. Keep the exception
# tied to exact test identifiers and exact digest shape; arbitrary detail fields
# remain subject to the credential detector.
PUBLIC_HASH_DETAIL_TEST_IDS = ("installed-config-hash", "installed-bundle-hash")

TEXT_SUFFIXES = {".py", ".cs", ".java", ".json", ".yaml", ".yml", ".md", ".ps1", ".sh",
                 ".txt", ".cpp", ".hpp", ".service", ".conf", ".xml", ".csv", ".lock"}


def tracked_files():
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=str(ROOT), universal_newlines=True)
    return [line for line in output.splitlines() if line]


def shannon_entropy(data):
    if not data:
        return 0.0
    counts = {}
    for byte in data:
        counts[byte] = counts.get(byte, 0) + 1
    total = float(len(data))
    return -sum((c / total) * math.log(c / total, 2) for c in counts.values())


def looks_like_raw_key(path, data):
    """A bare 32/64-byte high-entropy blob in a shipped file is a PSK shape."""
    if len(data) not in (32, 64):
        return False
    if path.suffix.lower() in TEXT_SUFFIXES:
        return False
    return shannon_entropy(data) > 4.2


def scan_bytes(label, data, findings, path=None):
    for name, pattern in PATTERNS:
        match = pattern.search(data)
        if match:
            # Never print the matched secret itself, only where it was found.
            findings.append("%s: %s at byte %d" % (label, name, match.start()))
    if path is not None and looks_like_raw_key(path, data):
        findings.append("%s: high-entropy %d-byte blob resembling raw key material" % (label, len(data)))


def scan_json_artifact(label, path, findings):
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError, UnicodeDecodeError):
        return

    def walk(node, trail, public_hash_detail=False):
        if isinstance(node, dict):
            legacy_hash_detail = (node.get("test_id") in PUBLIC_HASH_DETAIL_TEST_IDS and
                                  isinstance(node.get("detail"), str) and
                                  re.fullmatch("[0-9a-fA-F]{64}", node["detail"]) is not None)
            for key, value in node.items():
                walk(value, trail + "/" + str(key), legacy_hash_detail and key == "detail")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, trail + "/" + str(index))
        elif isinstance(node, str):
            leaf = trail.rsplit("/", 1)[-1]
            if leaf in PUBLIC_KEY_ID_FIELDS:
                return
            lowered = trail.lower()
            declared = any(marker in lowered for marker in HASH_TRAIL_MARKERS)
            if re.fullmatch("[0-9a-fA-F]{64}", node) and not declared and not public_hash_detail:
                findings.append("%s: 64 hex characters at %s outside a declared hash/id field" % (label, trail))
            if len(node) >= 24 and re.fullmatch("[A-Za-z0-9+/]+={0,2}", node):
                try:
                    decoded = base64.b64decode(node, validate=True)
                except Exception:
                    return
                if len(decoded) in (32, 64) and shannon_entropy(decoded) > 4.2:
                    # NuGet's lock format stores public SHA-512 package digests.
                    # Exempt this field and shape only, not the entire lock file.
                    if (path.name == "packages.lock.json" and isinstance(document, dict) and
                            document.get("version") == 1 and
                            re.fullmatch(r"/dependencies/[^/]+/[^/]+/contentHash", trail) and
                            len(decoded) == 64):
                        return
                    findings.append("%s: base64 blob decoding to %d high-entropy bytes at %s" % (label, len(decoded), trail))

    walk(document, "")


def scan_apk(path, findings):
    try:
        archive = zipfile.ZipFile(str(path))
    except (OSError, zipfile.BadZipFile):
        findings.append("%s: unreadable APK" % path.name)
        return
    with archive:
        for item in archive.infolist():
            if item.file_size > 4 * 1024 * 1024:
                continue
            try:
                data = archive.read(item)
            except (OSError, RuntimeError):
                continue
            scan_bytes("%s!%s" % (path.name, item.filename), data, findings)
        names = set(archive.namelist())
        for forbidden in ("assets/control.psk", "assets/phantom-secrets", "res/raw/control_psk"):
            if forbidden in names:
                findings.append("%s: credential material packaged at %s" % (path.name, forbidden))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-artifacts", action="store_true",
                        help="also audit build/ artifacts and APKs when present")
    args = parser.parse_args()

    findings = []
    scanned = 0
    for relative in tracked_files():
        if relative.startswith(SKIPPED_PREFIXES):
            continue
        if relative in FIXTURE_ALLOWLIST:
            continue
        path = ROOT / relative
        try:
            data = path.read_bytes()
        except OSError:
            continue
        scanned += 1
        scan_bytes(relative, data, findings, path)
        if path.suffix.lower() == ".json":
            scan_json_artifact(relative, path, findings)

    # Generated configuration, the CommissioningBundle and build manifests are the
    # artifacts TEST_PLAN names explicitly; audit them even when untracked.
    generated = []
    generated += sorted((ROOT / "config").glob("*/generated/*.json"))
    if args.include_artifacts:
        build = ROOT / "build"
        if build.is_dir():
            generated += sorted(build.rglob("build-manifest.json"))
            generated += sorted(build.rglob("*.build-manifest.json"))
    for path in generated:
        relative = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        scan_bytes(relative, data, findings, path)
        scan_json_artifact(relative, path, findings)

    apks = []
    if args.include_artifacts:
        quest = ROOT / "build" / "quest"
        if quest.is_dir():
            apks = sorted(quest.glob("*.apk"))
    for apk in apks:
        scan_apk(apk, findings)

    if findings:
        print("possible credential material:")
        for finding in sorted(set(findings)):
            print("  - " + finding)
        return 1
    print("provisioning audit PASS: %d repository files, %d generated artifacts, %d APKs; "
          "%d allowlisted synthetic fixtures" % (scanned, len(generated), len(apks), len(FIXTURE_ALLOWLIST)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
