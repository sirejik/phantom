#!/usr/bin/env python3
"""Fail-closed PC EV3 simulator speaking the normative HMAC protocol v1."""
import argparse,heapq,json,math,pathlib,random,secrets,socket,struct,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"protocol"))
import phantom_protocol as wire

TEST_KEY=bytes(range(32)); HOLD=6;TRACKING=7;SAFE_HOLD=8;STOPPED=9;FAULT_TIMEOUT=100;FAULT_REFERENCE=105
STATUS_BUNDLE=1<<2;STATUS_SAFETY=1<<4;STATUS_PAYLOAD=1<<7;STATUS_SAFE_SET=1<<8;STATUS_JOINT=1;STATUS_GRIPPER=2
SCENARIOS={"normal":{},"latency100":{"delay_ms":100},"loss5":{"loss":.05},"reorder":{"jitter_ms":80},"disconnect":{"disconnect":True},"stall":{"stall":True},"reference_loss":{"reference_loss":True},"local_stop":{"local_stop":True},"maintenance":{"maintenance":True}}

class Simulator:
    q_min=(-2.8,-1.2,0.0);q_max=(2.8,1.4,2.8);max_vel=(1.8,1.4,1.6);max_acc=(5.0,4.0,4.0)
    def __init__(self,scenario="normal",seed=7341,key=TEST_KEY):
        self.options=SCENARIOS[scenario];self.scenario=scenario;self.random=random.Random(seed);self.key=key;self.boot_id=bytes(self.random.randrange(256) for _ in range(16));self.session=None;self.client=None;self.client_nonce=None;self.last_sequence=0;self.tx_sequence=0;self.q=[0.,0.,.5];self.speed=[0.,0.,0.];self.target=list(self.q);self.grip=0.;self.grip_target=0.;self.state=HOLD;self.fault=0;self.references=False;self.bundle_hash=b"\x42"*32;self.safe_hash=b"\x53"*32;self.started=time.monotonic();self.last_command=self.started;self.queue=[];self.received=self.dropped=self.rejected=self.auth_failed=0;self.sample_id=0
    def discovery_record(self):return {"service":"_phantom-ev3._udp.local","instance":"PHANTOM-phantom01","robot_id":"phantom01","protocol_major":"1","controller_boot_id":self.boot_id.hex()}
    def queue_datagram(self,data,address,now):
        self.received+=1
        if self.random.random()<self.options.get("loss",0):self.dropped+=1;return
        delay=(self.options.get("delay_ms",0)+self.random.uniform(0,self.options.get("jitter_ms",0)))/1000;heapq.heappush(self.queue,(now+delay,self.received,data,address))
    def _send(self,name,payload,sequence=None):
        if sequence is None:self.tx_sequence+=1;sequence=self.tx_sequence
        return wire.encode(wire.NAMES[name]["type"],payload,self.key,self.session,self.boot_id,sequence,int((time.monotonic()-self.started)*1e6))
    def hello_ack(self,nonce):
        hashes=(wire.schema_hash(),self.bundle_hash,b"\x47"*32,b"\x44"*32,self.safe_hash,b"\x50"*32)
        payload=struct.pack("<16s32s32sHBB32s32s32s32s32s32s32sHHBBH3f3f3f3f",nonce,wire.id32("phantom01"),wire.id32("sim-v1"),0,0,0,b"\x11"*32,*hashes,HOLD,(STATUS_JOINT|STATUS_GRIPPER) if self.references else 0,0,3,0,*self.q_min,*self.q_max,*self.max_vel,*self.max_acc)
        return self._send("HELLO_ACK",payload,0)
    def calibration_sample(self,request_id):
        self.sample_id+=1;payload=struct.pack("<QQ4i4f4hHHQ",request_id,self.sample_id,*[round(x*1000) for x in self.q],0,*self.speed,0.,0,0,0,0,7600,0xF,int((time.monotonic()-self.started)*1e6));return self._send("CALIBRATION_SAMPLE",payload)
    def reference_ack(self,transaction_id,sample_id):
        self.references=True;payload=struct.pack("<QHHQ3ff",transaction_id,0,3,sample_id,*self.q,self.grip);return self._send("REFERENCE_ACK",payload)
    def telemetry(self,now):
        age=min(0xffffffff,int((now-self.last_command)*1000));status=STATUS_BUNDLE|STATUS_SAFETY|STATUS_PAYLOAD|STATUS_SAFE_SET|((STATUS_JOINT|STATUS_GRIPPER) if self.references else 0)
        payload=wire.telemetry_payload("phantom01","sim-v1",self.bundle_hash,self.safe_hash,self.state,self.fault,status,b"\0"*16,self.last_sequence,age,self.q,self.speed,self.grip,1 if self.references else 0,7600,0,"EMPTY",0,0);return self._send("TELEMETRY",payload)
    def process(self,data,address,now):
        try:packet=wire.decode(data,self.key)
        except wire.ProtocolError as exc:self.rejected+=1;self.auth_failed+=int(str(exc)=="HMAC");return []
        name=packet["message"];payload=packet["payload"]
        if name=="HELLO":
            robot=wire.read_id32(payload[:32]);nonce=payload[36:52]
            if robot!="phantom01" or packet["controller_boot_id"]!=self.boot_id:return []
            if self.client_nonce==nonce and self.client==address:return [(self.hello_ack(nonce),address)]
            self.session=bytes(self.random.randrange(1,256) for _ in range(16));self.client=address;self.client_nonce=nonce;self.last_sequence=0;self.tx_sequence=0;self.references=False;self.state=HOLD;return [(self.hello_ack(nonce),address)]
        if self.session is None or packet["session_id"]!=self.session or packet["controller_boot_id"]!=self.boot_id or packet["sequence"]<=self.last_sequence:self.rejected+=1;return []
        self.last_sequence=packet["sequence"]
        if name=="PING":return [(self._send("PONG",payload),address)]
        if name=="CALIBRATION_QUERY":return [(self.calibration_sample(struct.unpack("<Q",payload)[0]),address)]
        if name=="SET_JOINT_REFERENCE":
            transaction,bundle,drive,sample=struct.unpack_from("<Q32s32sQ",payload)
            if bundle!=self.bundle_hash or sample!=self.sample_id:self.rejected+=1;return []
            return [(self.reference_ack(transaction,sample),address)]
        if name=="COMMAND":
            flags,q0,q1,q2,grip,_=struct.unpack("<IffffI",payload);self.last_command=now
            if not self.references:self.state=SAFE_HOLD;self.fault=FAULT_REFERENCE;return []
            self.target=[max(lo,min(hi,q)) for q,lo,hi in zip((q0,q1,q2),self.q_min,self.q_max)];self.grip_target=grip;self.state=TRACKING if flags&1 and flags&4 and not flags&2 else HOLD
        return []
    def drain(self,now):
        out=[]
        while self.queue and self.queue[0][0]<=now:_,_,data,address=heapq.heappop(self.queue);out+=self.process(data,address,now)
        return out
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
    key=bytes.fromhex(args.psk_hex);sim=Simulator(args.scenario,args.seed,key);sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind((args.bind,args.port));sock.setblocking(False);record=sim.discovery_record();record["port"]=sock.getsockname()[1];print(json.dumps({"event":"listening",**record,"scenario":args.scenario}),flush=True);previous=telemetry_at=status_at=time.monotonic()
    try:
        while True:
            now=time.monotonic()
            try:
                while True:data,address=sock.recvfrom(2048);sim.queue_datagram(data,address,now)
            except BlockingIOError:pass
            for data,address in sim.drain(now):sock.sendto(data,address)
            sim.update(min(.05,now-previous),now);previous=now;disconnected=args.scenario=="disconnect" and 2<now-sim.started<5
            if sim.client and now>=telemetry_at and not disconnected:sock.sendto(sim.telemetry(now),sim.client);telemetry_at=now+.05
            if now>=status_at:print(json.dumps({"event":"status","state":sim.state,"fault":sim.fault,"reference":sim.references,"received":sim.received,"dropped":sim.dropped,"rejected":sim.rejected,"auth_failed":sim.auth_failed}),flush=True);status_at=now+1
            time.sleep(.002)
    except KeyboardInterrupt:pass

def main():
    p=argparse.ArgumentParser();p.add_argument("--bind",default="0.0.0.0");p.add_argument("--port",type=int,default=30470);p.add_argument("--scenario",choices=sorted(SCENARIOS),default="normal");p.add_argument("--seed",type=int,default=7341);p.add_argument("--psk-hex",default=TEST_KEY.hex(),help="test-only; production secrets are never CLI defaults");run(p.parse_args())
if __name__=="__main__":main()
