#!/usr/bin/env python3
"""Analyze pulled Phantom Quest JSONL without turning missing device data into evidence."""
import json
import math
import pathlib
import re
import statistics

TESTS = {
    "Q0_Environment": "Pinned Unity/OpenXR environment is available on device",
    "Q1_Multimodal": "Right hand and left Touch Plus remain valid simultaneously",
    "Q2_Grasp": "XR common grasp is stable and monotonic across requested closure",
    "Q3_WristVsPalm": "Wrist is more position-stable than Palm during wrist rotation/grasp",
    "Q4_RoomStability": "The recognized room frame remains stable across pause/recenter",
    "Q5_FixedQr": "A fixed QR has sufficient pose stability",
    "Q6_QrMatrix": "Marker detection is sufficient across size/distance/angle matrix",
    "Q7_MarkerRig": "Startup marker rig measures L1/L2 accurately",
    "Q8_UserShoulderFit": "Robust multi-arc fit produces repeatable shoulder/arm calibration",
    "Q9_Drift": "Absolute mapping has no cycle-dependent live drift",
    "Q10_TrackingPauseLoss": "Tracking loss/pause enters SAFE_HOLD and requires re-engage",
    "Q11_UdpSimulator": "Quest handles simulator network fault scenarios safely",
    "Q12_FullStartupDryRun": "Full room-to-simulator startup works end-to-end",
    "Q13_QrAbsoluteJointReference": "Rigid QR references provide repeatable absolute joint angles",
    "Q14_QrEncoderCrossCheck": "QR references and encoder zeroing agree across repeated cycles",
}

def percentile(values, fraction):
    values=sorted(values)
    return values[max(0,min(len(values)-1,math.ceil(len(values)*fraction)-1))] if values else float("nan")

def vector(payload, *path):
    value=payload
    try:
        for part in path: value=value[part]
        return (float(value["X"]),float(value["Y"]),float(value["Z"]))
    except (KeyError,TypeError,ValueError): return None

def distance(a,b): return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))

def quaternion(payload):
    try:
        value=(float(payload["RotationX"]),float(payload["RotationY"]),float(payload["RotationZ"]),float(payload["RotationW"]))
        norm=math.sqrt(sum(component*component for component in value))
        return tuple(component/norm for component in value) if norm>1e-12 else None
    except (KeyError,TypeError,ValueError): return None

def quaternion_angle_degrees(a,b):
    dot=abs(sum(x*y for x,y in zip(a,b)))
    return math.degrees(2.0*math.acos(max(-1.0,min(1.0,dot))))

def load(paths):
    events=[]
    for path in paths:
        with path.open("r",encoding="utf-8") as stream:
            for number,line in enumerate(stream,1):
                try:
                    event=json.loads(line)
                    raw=event.get("payload_json")
                    event["payload"]=json.loads(raw) if isinstance(raw,str) and raw else {}
                    event["source_file"]=str(path)
                    events.append(event)
                except (json.JSONDecodeError,TypeError) as error:
                    print(f"warning: {path}:{number}: {error}")
    return events

def run_ids(events): return sorted({e.get("run_id","") for e in events if e.get("run_id")})

def is_device_run(events):
    for event in events:
        payload=event.get("payload",{})
        if payload.get("platform") == "Android" and payload.get("device_model"):
            return True
    return False

def tracking_samples(events,test): return [e for e in events if e.get("test_id")==test and e.get("event_name")=="tracking_sample"]

def longest_false_streak_seconds(samples, field):
    start=None;last=None;longest=0.0
    for sample in sorted(samples,key=lambda e:e.get("monotonic_time_us",0)):
        timestamp=float(sample.get("monotonic_time_us",0))/1_000_000.0
        if not sample.get("payload",{}).get(field,False):
            if start is None:start=timestamp
            last=timestamp
        elif start is not None:
            longest=max(longest,max(0.0,(last or start)-start));start=last=None
    if start is not None:longest=max(longest,max(0.0,(last or start)-start))
    return longest

def room_id(status):
    # Runtime status is localized in current Quest builds. Match the UUID
    # without depending on the English or Russian text around it.
    match=re.search(r"(?:localized current room|комната)\s+([0-9a-fA-F-]{36})",status or "",re.IGNORECASE)
    return match.group(1).lower() if match else None

def completed_guided_run(events,test,phase_names):
    candidates=[]
    for candidate in {event.get("run_id") for event in events if event.get("test_id")==test}:
        run=[event for event in events if event.get("run_id")==candidate and event.get("test_id")==test]
        confirmed={event.get("state") for event in run if event.get("event_name")=="phase_confirmed_by_user"}
        if (any(event.get("event_name")=="sequence_complete" for event in run) and
            any(event.get("event_name")=="run_stop" for event in run) and
            set(phase_names).issubset(confirmed)):
            candidates.append((max((event.get("monotonic_time_us",0) for event in run),default=0),run))
    return max(candidates,key=lambda item:item[0])[1] if candidates else None

def evaluate(events,test):
    samples=tracking_samples(events,test)
    if not samples: return "NOT_MEASURED", "0 samples"
    if not is_device_run([e for e in events if e.get("run_id") in {s.get('run_id') for s in samples}]):
        return "INCONCLUSIVE", f"{len(samples)} samples, but no Android device metadata"
    if test=="Q0_Environment":
        phases=[f"step_{index}_of_4" for index in range(1,5)]
        run=completed_guided_run(events,test,phases)
        if not run:return "INCONCLUSIVE","guided 4-step MR/visual-stability sequence is incomplete"
        count=len([event for event in run if event.get("event_name")=="tracking_sample"])
        return "CONFIRMED",f"guided MR/visual-stability sequence completed; 4/4 user confirmations, n={count}"
    if test=="Q1_Multimodal":
        phases=[f"step_{index}_of_10" for index in range(1,11)]
        run=completed_guided_run(events,test,phases)
        if not run:return "INCONCLUSIVE","guided sequence incomplete"
        run_id=run[0].get("run_id")
        run_samples=[sample for sample in samples if sample.get("run_id")==run_id]
        # Steps 8-10 deliberately exercise focus and temporary input loss.
        steady_states={f"step_{index}_of_10" for index in range(1,8)}
        steady=[sample for sample in run_samples if sample.get("state") in steady_states]
        valid=0
        for sample in steady:
            p=sample["payload"]
            if p.get("RightHand",{}).get("Valid") and p.get("LeftController",{}).get("Valid"): valid+=1
        ratio=valid/len(steady) if steady else 0.0
        confirmations=[event for event in run if event.get("event_name")=="phase_confirmed_by_user"]
        recovered=sum(bool(event.get("payload",{}).get("BothValid")) for event in confirmations)
        loss_states={sample.get("state") for sample in run_samples if not (sample["payload"].get("RightHand",{}).get("Valid") and sample["payload"].get("LeftController",{}).get("Valid"))}
        expected_loss=bool({"step_8_of_10","step_9_of_10","step_10_of_10"}&loss_states)
        passed=ratio>=0.95 and recovered==10 and expected_loss
        return ("CONFIRMED" if passed else "REJECTED"), f"steady simultaneous-valid={ratio:.3f}, n={len(steady)}; recovery confirmations={recovered}/10; expected loss observed={expected_loss}"
    if test=="Q2_Grasp":
        phases=[f"repeat_{repeat}_{phase}" for repeat in range(1,6) for phase in ("OPEN","25","50","75","FIST","OPEN_RETURN")]
        run=completed_guided_run(events,test,phases)
        if not run:return "INCONCLUSIVE","guided 5-repeat sequence is incomplete"
        confirmed={event.get("state"):event.get("payload",{}).get("RightHand",{}).get("Grasp",{}) for event in run if event.get("event_name")=="phase_confirmed_by_user"}
        rows=[]
        for repeat in range(1,6):
            values=[]
            for phase in ("OPEN","25","50","75","FIST"):
                grasp=confirmed.get(f"repeat_{repeat}_{phase}",{})
                if not grasp.get("Ready") or not grasp.get("Valid"):
                    return "INCONCLUSIVE",f"invalid grasp at repeat {repeat} phase {phase}"
                values.append(float(grasp.get("Value01",0)))
            rows.append(values)
        monotonic_repeats=sum(all(row[index+1]>=row[index] for index in range(4)) for row in rows)
        open_values=[row[0] for row in rows];fist_values=[row[-1] for row in rows]
        passed=monotonic_repeats==5 and max(open_values)<=.25 and min(fist_values)>=.75
        return ("CONFIRMED" if passed else "REJECTED"), f"monotonic repeats={monotonic_repeats}/5; open range={min(open_values):.3f}-{max(open_values):.3f}; fist range={min(fist_values):.3f}-{max(fist_values):.3f}"
    if test=="Q3_WristVsPalm":
        wrist=[];palm=[]
        for sample in samples:
            w=vector(sample["payload"],"RightHand","Wrist","Position");p=vector(sample["payload"],"RightHand","Palm","Position")
            if w and p:wrist.append(w);palm.append(p)
        if len(wrist)<20:return "INCONCLUSIVE",f"only {len(wrist)} paired poses"
        wc=tuple(statistics.median(v[i] for v in wrist) for i in range(3));pc=tuple(statistics.median(v[i] for v in palm) for i in range(3))
        wd=[distance(v,wc) for v in wrist];pd=[distance(v,pc) for v in palm]
        wr=math.sqrt(statistics.mean(v*v for v in wd));pr=math.sqrt(statistics.mean(v*v for v in pd))
        return ("CONFIRMED" if wr<pr else "REJECTED"),f"wrist RMS/p95={wr:.5f}/{percentile(wd,.95):.5f} m; palm={pr:.5f}/{percentile(pd,.95):.5f} m; n={len(wd)}"
    if test=="Q4_RoomStability":
        instrumented=[sample for sample in samples if "room_ready" in sample.get("payload",{})]
        if not instrumented:
            return "INCONCLUSIVE",f"{len(samples)} device samples, but room_ready/status/floor_origin instrumentation is absent"
        phase_names={f"step_{index}_of_6" for index in range(1,7)}
        complete_runs=[]
        for candidate in {sample.get("run_id") for sample in instrumented}:
            candidate_samples=[sample for sample in instrumented if sample.get("run_id")==candidate]
            candidate_events=[e for e in events if e.get("run_id")==candidate and e.get("test_id")==test]
            sampled={sample.get("state") for sample in candidate_samples}
            confirmed={e.get("state") for e in candidate_events if e.get("event_name")=="phase_confirmed_by_user"}
            complete=any(e.get("event_name")=="sequence_complete" for e in candidate_events)
            stopped=any(e.get("event_name")=="run_stop" for e in candidate_events)
            if complete and stopped and phase_names.issubset(sampled) and phase_names.issubset(confirmed):
                latest=max((e.get("monotonic_time_us",0) for e in candidate_events),default=0)
                complete_runs.append((latest,candidate,candidate_samples,candidate_events))
        if complete_runs:
            _,_,samples,q4_events=max(complete_runs,key=lambda item:item[0])
        else:
            samples=instrumented
            run_set={sample.get("run_id") for sample in samples}
            q4_events=[e for e in events if e.get("run_id") in run_set and e.get("test_id")==test]
        sampled_phases={sample.get("state") for sample in samples}
        confirmed_phases={e.get("state") for e in q4_events if e.get("event_name")=="phase_confirmed_by_user"}
        complete=any(e.get("event_name")=="sequence_complete" for e in q4_events)
        stopped=any(e.get("event_name")=="run_stop" for e in q4_events)
        if not complete or not stopped or not phase_names.issubset(sampled_phases) or not phase_names.issubset(confirmed_phases):
            return "INCONCLUSIVE",f"guided sequence incomplete: sampled={len(phase_names & sampled_phases)}/6, confirmed={len(phase_names & confirmed_phases)}/6, complete={complete}, stopped={stopped}"
        ready=sum(bool(sample["payload"].get("room_ready")) for sample in samples)
        ready_ratio=ready/len(samples)
        recovery=longest_false_streak_seconds(samples,"room_ready")
        ids={value for value in (room_id(sample["payload"].get("room_status")) for sample in samples) if value}
        stationary_deviations=[]
        for phase in ("step_1_of_6","step_6_of_6"):
            floors=[vector(sample["payload"],"floor_origin") for sample in samples if sample.get("state")==phase and sample["payload"].get("room_ready")]
            floors=[value for value in floors if value and all(math.isfinite(component) for component in value)]
            if len(floors)<10:return "INCONCLUSIVE",f"only {len(floors)} valid floor samples in {phase}"
            center=tuple(statistics.median(value[index] for value in floors) for index in range(3))
            stationary_deviations.extend(distance(value,center) for value in floors)
        floor_p95=percentile(stationary_deviations,.95)
        passed=ready_ratio>=.95 and recovery<=15.0 and len(ids)==1 and floor_p95<=.02
        detail=f"room-ready={ready_ratio:.3f}, max recovery={recovery:.2f}s, room IDs={len(ids)}, stationary floor p95={floor_p95:.5f}m, n={len(samples)}"
        return ("CONFIRMED" if passed else "REJECTED"),detail
    if test=="Q5_FixedQr":
        instrumented=[sample for sample in samples if "qr" in sample.get("payload",{})]
        if not instrumented:return "INCONCLUSIVE",f"{len(samples)} device samples, but QR pose instrumentation is absent"
        complete_runs=[]
        for candidate in {sample.get("run_id") for sample in instrumented}:
            run_samples=[sample for sample in instrumented if sample.get("run_id")==candidate]
            capture_state="step_3_of_4" if any(sample.get("state")=="step_3_of_4" for sample in run_samples) else "step_2_of_3"
            candidate_samples=[sample for sample in run_samples if sample.get("state")==capture_state]
            candidate_events=[e for e in events if e.get("run_id")==candidate and e.get("test_id")==test]
            complete=any(e.get("event_name")=="sequence_complete" for e in candidate_events)
            stopped=any(e.get("event_name")=="run_stop" for e in candidate_events)
            if complete and stopped:
                latest=max((e.get("monotonic_time_us",0) for e in candidate_events),default=0)
                complete_runs.append((latest,candidate_samples,candidate_events))
        if not complete_runs:return "INCONCLUSIVE","instrumented Q5 run has not reached 500 valid poses and STOP/SAVE"
        _,capture,q5_events=max(complete_runs,key=lambda item:item[0])
        valid=[]
        for sample in capture:
            qr=sample.get("payload",{}).get("qr",{})
            position=vector(sample.get("payload",{}),"qr","PositionRoom")
            rotation=quaternion(qr)
            if qr.get("Valid") and position and rotation:valid.append((sample,qr,position,rotation))
        if len(valid)<500:return "INCONCLUSIVE",f"only {len(valid)} valid QR poses in completed capture"
        valid_rate=len(valid)/len(capture) if capture else 0.0
        center=tuple(statistics.median(item[2][index] for item in valid) for index in range(3))
        position_p95=percentile([distance(item[2],center) for item in valid],.95)
        reference=valid[0][3]
        aligned=[tuple(-component for component in item[3]) if sum(x*y for x,y in zip(item[3],reference))<0 else item[3] for item in valid]
        mean=tuple(statistics.mean(value[index] for value in aligned) for index in range(4))
        norm=math.sqrt(sum(component*component for component in mean));mean=tuple(component/norm for component in mean)
        orientation_p95=percentile([quaternion_angle_degrees(item[3],mean) for item in valid],.95)
        run_start=min((e.get("monotonic_time_us",0) for e in q5_events if e.get("event_name")=="run_start"),default=valid[0][0].get("monotonic_time_us",0))
        first_acquired=min((e.get("monotonic_time_us",0) for e in q5_events if e.get("event_name")=="qr_acquired"),default=valid[0][0].get("monotonic_time_us",0))
        first_detection=max(0.0,(first_acquired-run_start)/1_000_000.0)
        payloads={item[1].get("Payload","") for item in valid}
        passed=valid_rate>=.95 and position_p95<=.02 and orientation_p95<=2.0 and len(payloads)==1
        detail=f"payload={next(iter(payloads),'<none>')}, valid={len(valid)}/{len(capture)} ({valid_rate:.3f}), first detection={first_detection:.2f}s, position p95={position_p95:.5f}m, orientation p95={orientation_p95:.3f}deg"
        return ("CONFIRMED" if passed else "REJECTED"),detail
    return "INCONCLUSIVE", f"{len(samples)} device samples; required scenario-specific completion markers/ground truth absent"

def write_reports(events,out_dir):
    out_dir.mkdir(parents=True,exist_ok=True)
    ids=run_ids(events);rows=[]
    for test,hypothesis in TESTS.items():
        status,detail=evaluate(events,test);rows.append((test,hypothesis,status,detail))
    report=["# Quest Validation Report","",f"Analyzed run IDs: {', '.join(ids) if ids else 'none'}",f"Input events: {len(events)}","","No `CONFIRMED` verdict is emitted without Android device metadata and relevant samples.","","| Test | Hypothesis | Verdict | Evidence |","|---|---|---|---|"]
    report += [f"| {t} | {h} | **{s}** | {d} |" for t,h,s,d in rows]
    (out_dir/"QUEST_VALIDATION_REPORT.md").write_text("\n".join(report)+"\n",encoding="utf-8")
    recommendations=["# Quest Architecture Recommendations","","Evidence-driven status:",""]
    recommendations += [f"- {t}: {s} — {d}" for t,_,s,d in rows]
    recommendations += ["","Keep the pure mapping/IK/protocol boundaries. Do not transfer provisional calibration, QR thresholds, grasp curves, or multimodal assumptions into the specification until their device tests are CONFIRMED."]
    (out_dir/"QUEST_ARCHITECTURE_RECOMMENDATIONS.md").write_text("\n".join(recommendations)+"\n",encoding="utf-8")
    calibration=["# User Calibration Report","",f"Run IDs: {', '.join(sorted({e.get('run_id','') for e in events if e.get('test_id')=='Q8_UserShoulderFit' and e.get('run_id')})) or 'none'}","", "Status: **NOT_MEASURED**" if not tracking_samples(events,"Q8_UserShoulderFit") else "Status: **INCONCLUSIVE** — raw samples exist, but labeled normal/bent/coverage/head-rotation/body-step series and fit-result events are incomplete.","","Required matrix: 10 normal, 5 bent elbow, 5 insufficient coverage, 5 head-rotation-only, 3 body-step negatives."]
    (out_dir/"USER_CALIBRATION_REPORT.md").write_text("\n".join(calibration)+"\n",encoding="utf-8")
