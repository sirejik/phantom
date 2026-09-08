#!/usr/bin/env python3
"""Compute the normative content-addressed PHANTOM component build identity."""
import argparse
import hashlib
import json
import re

FIELDS=("schema","component_id","build_profile","source_tree_hash",
        "specification_sha256","protocol_schema_hash","component_config_hash",
        "toolchain_or_package_lock_hash")

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")

def identity(component,profile,source_tree_hash,specification_sha256,
             protocol_schema_hash,component_config_hash,toolchain_or_package_lock_hash):
    if component not in ("EV3","QUEST"): raise ValueError("component_id")
    if profile not in ("Release","Diagnostic","DeepDebug"): raise ValueError("build_profile")
    values=(source_tree_hash,specification_sha256,protocol_schema_hash,
            component_config_hash,toolchain_or_package_lock_hash)
    lengths=(64,64,64,64,64)
    for value,length in zip(values,lengths):
        if not isinstance(value,str) or not re.fullmatch("[0-9a-f]{%d}"%length,value):
            raise ValueError("identity input must be %d lowercase hex symbols"%length)
    obj={"schema":"PHANTOM-BUILD-V2","component_id":component,"build_profile":profile,
         "source_tree_hash":source_tree_hash,
         "specification_sha256":specification_sha256,"protocol_schema_hash":protocol_schema_hash,
         "component_config_hash":component_config_hash,
         "toolchain_or_package_lock_hash":toolchain_or_package_lock_hash}
    if tuple(sorted(obj))!=tuple(sorted(FIELDS)): raise AssertionError("identity field set")
    return hashlib.sha256(canonical(obj)).hexdigest(),obj

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--component",required=True,choices=("EV3","QUEST"))
    parser.add_argument("--profile",required=True,choices=("Release","Diagnostic","DeepDebug"))
    parser.add_argument("--source-tree-hash",required=True)
    parser.add_argument("--specification-sha256",required=True)
    parser.add_argument("--protocol-schema-hash",required=True)
    parser.add_argument("--component-config-hash",required=True)
    parser.add_argument("--toolchain-or-package-lock-hash",required=True)
    parser.add_argument("--print-object",action="store_true")
    args=parser.parse_args()
    digest,obj=identity(args.component,args.profile,args.source_tree_hash,
                        args.specification_sha256,args.protocol_schema_hash,
                        args.component_config_hash,args.toolchain_or_package_lock_hash)
    print(canonical(obj).decode("utf-8") if args.print_object else digest)

if __name__=="__main__":main()
