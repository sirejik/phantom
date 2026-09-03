#!/usr/bin/env python3
import argparse,json,math,pathlib
REQUIRED=("frame_id","receive_us","head","shoulder","wrist","grasp","left_grip")
def finite3(value):return isinstance(value,list) and len(value)==3 and all(isinstance(x,(int,float)) and math.isfinite(x) for x in value)
def validate(record):
    if any(k not in record for k in REQUIRED):raise ValueError("missing tracking field")
    for name in ("head","shoulder","wrist"):
        sample=record[name]
        if any(k not in sample for k in ("position_local_floor","valid","sample_or_query_us","receive_us","uncertainty_ms","quality")):raise ValueError(name+" metadata")
        if sample["valid"] and not finite3(sample["position_local_floor"]):raise ValueError(name+" position")
def pure_vector(record):
    s,w=record["shoulder"],record["wrist"]
    if not s["valid"] or not w["valid"]:return None
    return [w["position_local_floor"][i]-s["position_local_floor"][i] for i in range(3)]
def replay(path):
    count=valid=0
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():continue
        record=json.loads(line);validate(record);count+=1;valid+=pure_vector(record) is not None
    return {"records":count,"aligned_candidates":valid}
def main():
    p=argparse.ArgumentParser();p.add_argument("recording");args=p.parse_args();print(json.dumps(replay(args.recording),sort_keys=True))
if __name__=="__main__":main()
