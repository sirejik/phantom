#!/usr/bin/env python3
"""Describe exact ZIP-entry differences between two Quest APK builds."""
import argparse
import hashlib
import json
import pathlib
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def describe(left_path, right_path):
    with zipfile.ZipFile(left_path) as left, zipfile.ZipFile(right_path) as right:
        left_entries = {item.filename: left.read(item) for item in left.infolist()}
        right_entries = {item.filename: right.read(item) for item in right.infolist()}
    common_differences = []
    for name in sorted(set(left_entries) & set(right_entries)):
        if left_entries[name] != right_entries[name]:
            common_differences.append({
                "name": name,
                "left_sha256": digest(left_entries[name]),
                "right_sha256": digest(right_entries[name]),
            })
    left_only = {digest(left_entries[name]): name for name in set(left_entries) - set(right_entries)}
    right_only = {digest(right_entries[name]): name for name in set(right_entries) - set(left_entries)}
    renamed = [
        {"left_name": left_only[value], "right_name": right_only[value], "content_sha256": value}
        for value in sorted(set(left_only) & set(right_only))
    ]
    unmatched_left = sorted(name for value, name in left_only.items() if value not in right_only)
    unmatched_right = sorted(name for value, name in right_only.items() if value not in left_only)
    return {
        "comparison": "ZIP_ENTRY_CONTENT",
        "common_entry_differences": common_differences,
        "renamed_equal_content_entries": renamed,
        "unmatched_left_entries": unmatched_left,
        "unmatched_right_entries": unmatched_right,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("left", type=pathlib.Path)
    parser.add_argument("right", type=pathlib.Path)
    args = parser.parse_args()
    print(json.dumps(describe(args.left, args.right), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
