#!/usr/bin/env python3
"""Fail-closed PC EV3 simulator speaking the normative HMAC protocol v1."""
import argparse,hashlib,heapq,json,math,pathlib,random,secrets,socket,struct,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"protocol"))
import phantom_protocol as wire

TEST_KEY=bytes(range(32)); STATES=wire.SCHEMA["enums"]["State"];FAULTS=wire.SCHEMA["enums"]["Fault"]
DISCOVERY=STATES["DISCOVERY"];CONNECTED_UNREFERENCED=STATES["CONNECTED_UNREFERENCED"];HOLD=STATES["HOLD"];TRACKING=STATES["TRACKING"];SAFE_HOLD=STATES["SAFE_HOLD"];STOPPED=STATES["STOPPED"];FAULT_TIMEOUT=FAULTS["FAULT_TIMEOUT"];FAULT_REFERENCE=FAULTS["FAULT_REFERENCE"];ERR_CONTROL_SESSION_BUSY=wire.SCHEMA["enums"]["ResultCode"]["ERR_CONTROL_SESSION_BUSY"]
STATUS_BITS=wire.SCHEMA["bitfields"]["telemetry_status_flags"];STATUS_BUNDLE=1<<STATUS_BITS["COMMISSIONING_BUNDLE_VALID"];STATUS_SAFETY=1<<STATUS_BITS["SAFETY_SUPERVISOR_ALIVE"];STATUS_PAYLOAD=1<<STATUS_BITS["PAYLOAD_PROFILE_VALID"];STATUS_SAFE_SET=1<<STATUS_BITS["ACTIVE_JOINT_SAFE_SET_VALID"];STATUS_JOINT=1<<STATUS_BITS["JOINT_REFERENCE_VALID"];STATUS_GRIPPER=1<<STATUS_BITS["GRIPPER_REFERENCE_VALID"]
NETWORK_BUILD_ID=hashlib.sha256(b"PHANTOM-SIM-STAGE3").digest();FULL_BUILD_ID=hashlib.sha256(b"PHANTOM-SIM-V1").digest()
SCENARIOS={"normal":{},"latency100":{"delay_ms":100},"loss5":{"loss":.05},"reorder":{"jitter_ms":80},"disconnect":{"disconnect":True},"stall":{"stall":True},"reference_loss":{"reference_loss":True},"local_stop":{"local_stop":True},"maintenance":{"maintenance":True},"hello_ack_lost":{"drop_first_ack":True},"busy":{"busy":True},"telemetry_stop_resume":{"telemetry_pause":True},"bad_hmac":{"bad_hmac":True},"wrong_robot":{"wrong_robot":True},"wrong_protocol":{"wrong_protocol":True},"wrong_schema_hash":{"wrong_schema":True},"wrong_bundle_hash":{"wrong_bundle":True},"duplicate_packet":{"duplicate":True},"stale_packet":{"stale":True},"controller_boot_change":{"boot_change":True},"endpoint_update":{"endpoint_update":True},"service_remove_readd":{"service_remove_readd":True}}

class Simulator:
    q_min=(-2.8,-1.2,0.0);q_max=(2.8,1.4,2.8);max_vel=(1.8,1.4,1.6);max_acc=(5.0,4.0,4.0)
    def __init__(self,scenario="normal",seed=7341,key=TEST_KEY,network_only=False):
        self.options=SCENARIOS[scenario];self.scenario=scenario;self.network_only=network_only;self.random=random.Random(seed);self.key=key;self.boot_id=bytes(self.random.randrange(256) for _ in range(16));self.session=None;self.client=None;self.client_nonce=None;self.last_sequence=0;self.tx_sequence=0;self.q=[0.,0.,.5];self.speed=[0.,0.,0.];self.target=list(self.q);self.grip=0.;self.grip_target=0.;self.state=DISCOVERY if network_only else HOLD;self.fault=0;self.references=False;self.bundle_hash=self.network_bundle_hash() if network_only else b"\x42"*32;self.safe_hash=b"\x00"*32 if network_only else b"\x53"*32;self.started=time.monotonic();self.last_command=self.started;self.last_session_rx=self.started;self.session_stale=2.;self.queue=[];self.received=self.dropped=self.rejected=self.auth_failed=0;self.sample_id=0;self.hello_count=0;self.boot_changed=False;self.corrupt_sent=False;self.previous_telemetry=None
    @staticmethod
    def network_bundle_hash():return hashlib.sha256((ROOT/"config"/"generated"/"commissioning_bundle-network-only.generated.json").read_bytes().rstrip(b"\r\n")).digest()
    def discovery_record(self):return {"service":"_phantom-ev3._udp.local.","instance":"PHANTOM-phantom01","robot_id":"phantom01","protocol_major":"1","controller_boot_id":self.boot_id.hex(),"build_id":(NETWORK_BUILD_ID if self.network_only else FULL_BUILD_ID).hex()}
    def queue_datagram(self,data,address,now):
        self.received+=1
        if self.random.random()<self.options.get("loss",0):self.dropped+=1;return
        delay=(self.options.get("delay_ms",0)+self.random.uniform(0,self.options.get("jitter_ms",0)))/1000;heapq.heappush(self.queue,(now+delay,self.received,data,address))
    def _send(self,name,payload,sequence=None):
        if sequence is None:self.tx_sequence+=1;sequence=self.tx_sequence
        return wire.encode(wire.NAMES[name]["type"],payload,self.key,self.session,self.boot_id,sequence,int((time.monotonic()-self.started)*1e6))
    def hello_ack(self,nonce,result=0,session_id=None):
        protocol_hash=b"\xee"*32 if self.options.get("wrong_schema") else wire.schema_hash();bundle_hash=b"\xdd"*32 if self.options.get("wrong_bundle") else self.bundle_hash
        hashes=(protocol_hash,bundle_hash,b"\0"*32 if self.network_only else b"\x47"*32,b"\0"*32 if self.network_only else b"\x44"*32,self.safe_hash,b"\0"*32 if self.network_only else b"\x50"*32)
        robot="phantom99" if self.options.get("wrong_robot") else "phantom01";minor=1 if self.options.get("wrong_protocol") else 0;profile=1 if self.network_only else 0;state=CONNECTED_UNREFERENCED if self.network_only else HOLD;reference=0 if self.network_only else (STATUS_JOINT|STATUS_GRIPPER) if self.references else 0;limits=(0.,)*12 if self.network_only else (*self.q_min,*self.q_max,*self.max_vel,*self.max_acc)
        payload=struct.pack("<16s32s32sHBB32s32s32s32s32s32s32sHHBBH3f3f3f3f",nonce,wire.id32(robot),NETWORK_BUILD_ID if self.network_only else FULL_BUILD_ID,minor,0,0,b"\x11"*32,*hashes,state,reference,profile,0 if self.network_only else 3,result,*limits)
        bound=self.session if session_id is None else session_id
        return wire.encode(wire.NAMES["HELLO_ACK"]["type"],payload,self.key,bound,self.boot_id,0,int((time.monotonic()-self.started)*1e6))
    def calibration_sample(self,request_id):
        self.sample_id+=1;payload=struct.pack("<QQ4i4f4hHHQ",request_id,self.sample_id,*[round(x*1000) for x in self.q],0,*self.speed,0.,0,0,0,0,7600,0xF,int((time.monotonic()-self.started)*1e6));return self._send("CALIBRATION_SAMPLE",payload)
    def reference_ack(self,transaction_id,sample_id):
        self.references=True;payload=struct.pack("<QHHQ3ff",transaction_id,0,3,sample_id,*self.q,self.grip);return self._send("REFERENCE_ACK",payload)
    def telemetry(self,now):
        age=0xffffffff if self.network_only else min(0xffffffff,int((now-self.last_command)*1000));status=STATUS_BUNDLE|(0 if self.network_only else STATUS_SAFETY|STATUS_PAYLOAD|STATUS_SAFE_SET|((STATUS_JOINT|STATUS_GRIPPER) if self.references else 0));q=(0.,0.,0.) if self.network_only else self.q;speed=(0.,0.,0.) if self.network_only else self.speed;grip=0. if self.network_only else self.grip;grip_state=0 if self.network_only else 1 if self.references else 0
        payload=wire.telemetry_payload("phantom01",NETWORK_BUILD_ID if self.network_only else FULL_BUILD_ID,self.bundle_hash,self.safe_hash,self.state,self.fault,status,b"\0"*16,self.last_sequence,age,q,speed,grip,grip_state,7600,0,"UNSELECTED" if self.network_only else "EMPTY",2 if self.network_only else 0,1 if self.network_only else 0);return self._send("TELEMETRY",payload)
    def process(self,data,address,now):
        try:packet=wire.decode(data,self.key)
        except wire.ProtocolError as exc:self.rejected+=1;self.auth_failed+=int(str(exc)=="HMAC");return []
        name=packet["message"];payload=packet["payload"]
        if name=="HELLO":
            robot=wire.read_id32(payload[:32]);nonce=payload[36:52]
            if robot!="phantom01" or packet["controller_boot_id"]!=self.boot_id:return []
            self.hello_count+=1
            if self.client_nonce==nonce and self.client==address:return [(self.hello_ack(nonce),address)]
            if self.options.get("busy") or self.session is not None and now-self.last_session_rx<=self.session_stale:
                return [(self.hello_ack(nonce,ERR_CONTROL_SESSION_BUSY,b"\0"*16),address)]
            self.session=bytes(self.random.randrange(1,256) for _ in range(16));self.client=address;self.client_nonce=nonce;self.last_sequence=0;self.tx_sequence=0;self.references=False;self.state=CONNECTED_UNREFERENCED if self.network_only else HOLD
            self.last_session_rx=now
            if self.options.get("drop_first_ack") and self.hello_count==1:return []
            return [(self.hello_ack(nonce),address)]
        if self.session is None or packet["session_id"]!=self.session or packet["controller_boot_id"]!=self.boot_id or packet["sequence"]<=self.last_sequence:self.rejected+=1;return []
        self.last_sequence=packet["sequence"];self.last_session_rx=now
        if name=="PING":return [(self._send("PONG",payload),address)]
        if name=="CALIBRATION_QUERY":return [(self.calibration_sample(struct.unpack("<Q",payload)[0]),address)]
        if name=="SET_JOINT_REFERENCE":
            transaction,bundle,drive,sample=struct.unpack_from("<Q32s32sQ",payload)
            if bundle!=self.bundle_hash or sample!=self.sample_id:self.rejected+=1;return []
            return [(self.reference_ack(transaction,sample),address)]
        if name=="COMMAND":
            if self.network_only:return []
            flags,q0,q1,q2,grip,_=struct.unpack("<IffffI",payload);self.last_command=now
            if not self.references:self.state=SAFE_HOLD;self.fault=FAULT_REFERENCE;return []
            self.target=[max(lo,min(hi,q)) for q,lo,hi in zip((q0,q1,q2),self.q_min,self.q_max)];self.grip_target=grip;self.state=TRACKING if flags&1 and flags&4 and not flags&2 else HOLD
        return []
    def drain(self,now):
        out=[]
        while self.queue and self.queue[0][0]<=now:_,_,data,address=heapq.heappop(self.queue);out+=self.process(data,address,now)
        return out
    def restart_controller(self):
        self.boot_id=bytes(self.random.randrange(1,256) for _ in range(16));self.session=None;self.client=None;self.client_nonce=None;self.last_sequence=0;self.tx_sequence=0;self.state=DISCOVERY if self.network_only else HOLD;self.boot_changed=True
    def update(self,dt,now):
        if self.references and now-self.last_command>.120:self.state=SAFE_HOLD;self.fault=FAULT_TIMEOUT
        elapsed=now-self.started
        if self.options.get("reference_loss") and elapsed>2:self.references=False;self.state=SAFE_HOLD;self.fault=FAULT_REFERENCE
        if self.options.get("local_stop") and elapsed>2:self.state=STOPPED
        if self.options.get("maintenance") and elapsed>2:self.state=SAFE_HOLD;self.fault=103
        for i in range(3):
            desired=max(-self.max_vel[i],min(self.max_vel[i],(self.target[i]-self.q[i])*8)) if self.state==TRACKING and not self.options.get("stall") else 0
            delta=max(-self.max_acc[i]*dt,min(self.max_acc[i]*dt,desired-self.speed[i]));self.speed[i]+=delta;self.q[i]=max(self.q_min[i],min(self.q_max[i],self.q[i]+self.speed[i]*dt))
        self.grip+=(self.grip_target-self.grip)*min(1,dt*8)

def run(args):
    key=bytes.fromhex(args.psk_hex);sim=Simulator(args.scenario,args.seed,key,args.network_only);sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind((args.bind,args.port));sock.setblocking(False);record=sim.discovery_record();record["port"]=sock.getsockname()[1];print(json.dumps({"event":"listening",**record,"scenario":args.scenario,"network_only":args.network_only}),flush=True);previous=telemetry_at=status_at=time.monotonic();endpoint_changed=False;service_removed=False;service_readded=False
    try:
        while True:
            now=time.monotonic()
            try:
                while True:data,address=sock.recvfrom(2048);sim.queue_datagram(data,address,now)
            except BlockingIOError:pass
            for data,address in sim.drain(now):sock.sendto(data,address)
            sim.update(min(.05,now-previous),now);previous=now;elapsed=now-sim.started
            if sim.options.get("endpoint_update") and elapsed>2 and not endpoint_changed:
                sock.close();sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind((args.bind,0));sock.setblocking(False);endpoint_changed=True;record=sim.discovery_record();record["port"]=sock.getsockname()[1];print(json.dumps({"event":"service_updated",**record}),flush=True)
            if sim.options.get("service_remove_readd") and elapsed>2 and not service_removed:
                service_removed=True;print(json.dumps({"event":"service_removed","instance":"PHANTOM-phantom01"}),flush=True)
            if sim.options.get("service_remove_readd") and elapsed>4 and not service_readded:
                service_readded=True;record=sim.discovery_record();record["port"]=sock.getsockname()[1];print(json.dumps({"event":"service_added",**record}),flush=True)
            disconnected=(args.scenario=="disconnect" and 2<elapsed<5) or (service_removed and not service_readded);paused=sim.options.get("telemetry_pause") and 1<elapsed<3
            if sim.options.get("boot_change") and elapsed>2 and not sim.boot_changed:sim.restart_controller();print(json.dumps({"event":"controller_boot_changed",**sim.discovery_record()}),flush=True)
            if sim.client and now>=telemetry_at and not disconnected and not paused:
                data=sim.telemetry(now)
                if sim.options.get("bad_hmac") and not sim.corrupt_sent:data=data[:-1]+bytes([data[-1]^1]);sim.corrupt_sent=True
                sock.sendto(data,sim.client)
                if sim.options.get("duplicate"):sock.sendto(data,sim.client)
                if sim.options.get("stale") and sim.previous_telemetry is not None:sock.sendto(sim.previous_telemetry,sim.client)
                sim.previous_telemetry=data;telemetry_at=now+.05
            if now>=status_at:print(json.dumps({"event":"status","state":sim.state,"fault":sim.fault,"reference":sim.references,"received":sim.received,"dropped":sim.dropped,"rejected":sim.rejected,"auth_failed":sim.auth_failed}),flush=True);status_at=now+1
            time.sleep(.002)
    except KeyboardInterrupt:pass

def main():
    p=argparse.ArgumentParser();p.add_argument("--bind",default="0.0.0.0");p.add_argument("--port",type=int,default=30470);p.add_argument("--scenario",choices=sorted(SCENARIOS),default="normal");p.add_argument("--seed",type=int,default=7341);p.add_argument("--network-only",action="store_true");p.add_argument("--psk-hex",default=TEST_KEY.hex(),help="test-only; production secrets are never CLI defaults");run(p.parse_args())
if __name__=="__main__":main()
