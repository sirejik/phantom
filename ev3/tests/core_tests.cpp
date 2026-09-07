#include "phantom/controller_core.hpp"
#include "phantom/event_log.hpp"
#include "phantom/json_reader.hpp"
#include "phantom/runtime_guard.hpp"
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <iostream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

static int failures=0;
static void check(bool ok,const char*message){if(!ok){std::cerr<<"FAIL: "<<message<<"\n";++failures;}}

namespace {
class FailingBackend final:public phantom::MotorBackend{
public:
  bool initialize(std::string&error)override{error="injected I/O failure";return false;}
  phantom::IoSnapshot read()noexcept override{return {};}
  bool set_duty(std::size_t,std::int16_t)noexcept override{return false;}
  void brake_all()noexcept override{++brakes;}
  int brakes=0;
};

phantom::RuntimeConfig network_only_config(){
  phantom::RuntimeConfig config;
  config.qualification_only=true;config.actuator_scope_mask=0;config.safety_observation_mask=0;
  return config;
}

// Drives the core through `count` nominal 20 ms ticks with a live supervisor.
void run_ticks(phantom::ControllerCore& core,std::uint64_t& now,int count){
  for(int i=0;i<count;++i){now+=20000;core.set_safety_heartbeat_alive(true);core.tick(now,20000);}
}
}

int main(){
  // ---- startup admission ---------------------------------------------------
  {
    phantom::MockMotorBackend backend;phantom::RuntimeConfig blocked;
    phantom::ControllerCore core(backend,blocked);
    check(core.initialize(),"healthy backend must initialize while commissioning stays blocked");
    check(core.state()==phantom::State::SafeHold&&core.fault()==phantom::Fault::Config,"uncommissioned startup must enter SAFE_HOLD/CONFIG");
    std::uint64_t now=1000000;
    core.set_safety_heartbeat_alive(true);core.tick(now,20000);
    check(backend.nonzero_writes()==0,"startup generated motor output");
    check(!core.motion_allowed(),"startup allowed motion");
    phantom::Target target;target.sequence=1;target.motion_flags=5;target.q={{0,0,0}};target.grip=0.5f;target.received_us=now;
    check(core.publish_target(target),"valid bounded target rejected");
    now+=20000;core.set_safety_heartbeat_alive(true);core.tick(now,20000);
    check(backend.nonzero_writes()==0,"unreferenced target generated motor output");
  }
  // ---- backend failure fails closed ---------------------------------------
  {
    FailingBackend failing;phantom::RuntimeConfig blocked;phantom::ControllerCore core(failing,blocked);
    check(!core.initialize(),"backend failure was accepted");
    check(core.state()==phantom::State::SafeHold&&core.fault()==phantom::Fault::Config,"backend failure did not fail closed");
    check(core.initialization_error()=="injected I/O failure","backend error was not preserved");
    check(failing.brakes>0,"backend failure did not invoke brake path");
  }
  // ---- LOCAL_STOP latches and only RESET_STOPPED clears it (C-02) ----------
  {
    phantom::MockMotorBackend backend;phantom::ControllerCore core(backend,network_only_config());
    check(core.initialize(),"network-only initialization failed");
    std::uint64_t now=1000000;run_ticks(core,now,3);
    check(core.state()==phantom::State::Discovery,"network-only idle state");
    backend.set_local_stop(true);run_ticks(core,now,1);
    check(core.state()==phantom::State::Stopped&&core.stop_latched(),"LOCAL_STOP did not latch STOPPED");
    check(core.request_reset_stopped()==phantom::RecoveryResult::StopStillEngaged,"reset accepted while stop is still engaged");
    backend.set_local_stop(false);run_ticks(core,now,5);
    check(core.state()==phantom::State::Stopped&&core.stop_latched(),"release alone cleared the stop latch");
    check(core.request_reset_stopped()==phantom::RecoveryResult::Ok,"valid RESET_STOPPED rejected");
    check(!core.stop_latched()&&!core.motion_allowed(),"RESET_STOPPED armed motion");
    run_ticks(core,now,1);
    check(core.state()==phantom::State::Discovery,"recovery did not return to the session-derived state");
    check(core.request_reset_stopped()==phantom::RecoveryResult::NotLatched,"RESET_STOPPED accepted without a latch");
    check(backend.nonzero_writes()==0,"stop/recovery generated motor output");
  }
  // ---- supervisor loss is a latched STOPPED even at scope 0x00 (H-06) ------
  {
    phantom::MockMotorBackend backend;phantom::ControllerCore core(backend,network_only_config());
    check(core.initialize(),"network-only initialization failed");
    std::uint64_t now=1000000;run_ticks(core,now,3);
    now+=20000;core.set_safety_heartbeat_alive(false);core.tick(now,20000);
    check(core.state()==phantom::State::Stopped,"supervisor loss must force STOPPED");
    check(core.fault()==phantom::Fault::ControllerProcess,"supervisor loss must raise FAULT_CONTROLLER_PROCESS");
    check(core.fault_latched(),"supervisor loss must latch");
    now+=20000;core.set_safety_heartbeat_alive(true);core.tick(now,20000);
    check(core.state()==phantom::State::Stopped,"latched fault cleared itself when the supervisor returned");
    check(core.acknowledge_fault((std::uint16_t)phantom::Fault::Timeout)!=phantom::RecoveryResult::Ok,"FAULT_ACK accepted the wrong code");
    check(core.acknowledge_fault((std::uint16_t)phantom::Fault::ControllerProcess)==phantom::RecoveryResult::Ok,"valid FAULT_ACK rejected");
    check(!core.fault_latched()&&!core.motion_allowed(),"FAULT_ACK armed motion");
    check(backend.nonzero_writes()==0,"supervisor loss generated motor output");
  }
  // ---- startup grace: never-seen supervisor must not latch instantly -------
  {
    phantom::MockMotorBackend backend;phantom::ControllerCore core(backend,network_only_config());
    check(core.initialize(),"network-only initialization failed");
    std::uint64_t now=1000000;
    core.set_safety_heartbeat_alive(false);core.tick(now,20000);
    check(core.state()!=phantom::State::Stopped,"boot grace window is missing");
    now+=2000000;core.set_safety_heartbeat_alive(false);core.tick(now,20000);
    check(core.state()==phantom::State::Stopped,"supervisor never appeared and was not treated as lost");
  }
  // ---- two-level loop policy (H-04) ---------------------------------------
  {
    phantom::MockMotorBackend backend;phantom::RuntimeConfig config=network_only_config();
    config.loop_safe_hold_ms=60;config.loop_fault_ms=100;
    phantom::ControllerCore core(backend,config);
    check(core.initialize(),"network-only initialization failed");
    std::uint64_t now=1000000;run_ticks(core,now,3);
    now+=70000;core.set_safety_heartbeat_alive(true);core.tick(now,70000);
    check(core.state()==phantom::State::SafeHold&&core.fault()==phantom::Fault::None,"loop_safe_hold_ms threshold did not fire");
    now+=120000;core.set_safety_heartbeat_alive(true);core.tick(now,120000);
    check(core.state()==phantom::State::SafeHold&&core.fault()==phantom::Fault::LoopOverrun,"loop_fault_ms threshold did not raise FAULT_LOOP_OVERRUN");
    run_ticks(core,now,1);
    check(core.state()==phantom::State::Discovery,"loop overrun did not recover once timing returned");
    check(core.snapshot().loop_health_flags!=0,"loop health flags were not recorded");
  }
  // ---- telemetry snapshot is controller-owned (H-01) -----------------------
  {
    phantom::MockMotorBackend backend;phantom::ControllerCore core(backend,network_only_config());
    check(core.initialize(),"network-only initialization failed");
    std::uint64_t now=1000000;run_ticks(core,now,2);
    const phantom::TelemetrySnapshot& idle=core.snapshot();
    check(idle.state==(std::uint16_t)phantom::State::Discovery,"snapshot state does not follow the controller");
    check((idle.status_flags&phantom::wire::kTelemetryStatusFlagsSafetySupervisorAlive)!=0,"supervisor-alive flag missing");
    check((idle.status_flags&phantom::wire::kTelemetryStatusFlagsLocalStopActive)==0,"local-stop flag set while released");
    check(idle.q_actual[0]==0.0f&&idle.q_speed[0]==0.0f&&idle.grip_actual==0.0f,"scope-zero observation fields are not canonical zero");
    core.set_network_session_active(true);run_ticks(core,now,1);
    check(core.snapshot().state==(std::uint16_t)phantom::State::ConnectedUnreferenced,"snapshot did not follow the session");
    backend.set_local_stop(true);run_ticks(core,now,1);
    check(core.snapshot().state==(std::uint16_t)phantom::State::Stopped,"snapshot did not report STOPPED");
    check((core.snapshot().status_flags&phantom::wire::kTelemetryStatusFlagsLocalStopActive)!=0,"local-stop flag not reported");
    bool incident_id_set=false;for(std::uint8_t byte:core.snapshot().incident_id)incident_id_set=incident_id_set||byte!=0;
    check(incident_id_set,"latched incident did not assign an incident id");
    check(core.incident_pending(),"latched incident did not request a flight-recorder export");
  }
  // ---- flight recorder honours configured depth ---------------------------
  {
    phantom::MockMotorBackend backend;phantom::RuntimeConfig config=network_only_config();
    config.flight_recorder_samples=8;
    phantom::ControllerCore core(backend,config);
    check(core.initialize(),"network-only initialization failed");
    check(core.recorder().capacity()==8,"flight recorder ignored configured depth");
    std::uint64_t now=1000000;run_ticks(core,now,20);
    check(core.recorder().size()==8,"flight recorder is not bounded by configuration");
    check(core.recorder().at(0).monotonic_us<core.recorder().newest().monotonic_us,"flight recorder order is wrong");
  }
  // ---- duty conversion is explicit and symmetric (I-03) -------------------
  {
    check(phantom::Ev3SysfsBackend::permille_to_percent(0)==0,"duty 0");
    check(phantom::Ev3SysfsBackend::permille_to_percent(1000)==100,"duty +1000");
    check(phantom::Ev3SysfsBackend::permille_to_percent(-1000)==-100,"duty -1000");
    check(phantom::Ev3SysfsBackend::permille_to_percent(2000)==100,"duty clamp high");
    check(phantom::Ev3SysfsBackend::permille_to_percent(-2000)==-100,"duty clamp low");
    check(phantom::Ev3SysfsBackend::permille_to_percent(45)==5,"duty rounds to nearest");
    check(phantom::Ev3SysfsBackend::permille_to_percent(-45)==-5,"duty rounds symmetrically");
    check(phantom::Ev3SysfsBackend::permille_to_percent(4)==0,"duty below half a percent");
  }
  // ---- bounded JSON reader -------------------------------------------------
  {
    phantom::JsonValue root;std::string error;
    check(phantom::parse_json("{\"a\":{\"b\":12},\"c\":[1,2],\"d\":true,\"e\":\"x\"}",root,error),"valid JSON rejected");
    std::uint64_t value=0;bool flag=false;std::string text;
    check(phantom::json_uint(root,"a/b",0,100,value)&&value==12,"nested integer");
    check(!phantom::json_uint(root,"a/b",20,100,value),"range check missing");
    check(phantom::json_bool(root,"d",flag)&&flag,"boolean");
    check(phantom::json_string(root,"e",text)&&text=="x","string");
    check(!phantom::json_uint(root,"missing",0,100,value),"absent path must fail closed");
    phantom::JsonValue other;
    check(!phantom::parse_json("{\"a\":1,\"a\":2}",other,error),"duplicate object key accepted");
    check(!phantom::parse_json("{\"a\":1",other,error),"truncated JSON accepted");
    check(!phantom::parse_json("{}trailing",other,error),"trailing bytes accepted");
    check(!phantom::parse_json(std::string(300000,'x'),other,error),"oversized document accepted");
  }
  // ---- heartbeat, lease and bounded drain ---------------------------------
  {
    const std::string prefix="/tmp/phantom-guard-test-"+std::to_string((long long)::getpid());
    const std::string a=prefix+"-a.sock",b=prefix+"-b.sock",lock=prefix+".lock";
    {
      phantom::HeartbeatChannel first(a,b,1),second(b,a,2);
      check(first.valid()&&second.valid(),"heartbeat socket setup");
      const auto now=phantom::monotonic_us();
      first.send(now);second.drain(now+1);
      check(second.peer_fresh(now+1,100000),"heartbeat not received");
      // A flood must be bounded: at most 16 datagrams are consumed per drain.
      for(int i=0;i<64;++i)first.send(now);
      second.drain(now+2);
      check(second.peer_fresh(now+2,100000),"bounded drain lost liveness");
      phantom::MotorLease lease1(lock.c_str()),lease2(lock.c_str());
      check(lease1.try_acquire(),"first lease failed");
      check(!lease2.try_acquire(),"split-brain lease allowed");
      lease1.release();
      check(lease2.try_acquire(),"lease takeover failed");
    }
    ::unlink(lock.c_str());
  }
  // ---- log retention -------------------------------------------------------
  {
    const std::string directory="/tmp/phantom-log-test-"+std::to_string((long long)::getpid());
    ::mkdir(directory.c_str(),0700);
    for(int i=0;i<3;++i){
      const std::string path=directory+"/incident-"+std::to_string(i)+".jsonl";
      int fd=::open(path.c_str(),O_WRONLY|O_CREAT|O_TRUNC,0600);
      if(fd>=0){std::string blob(600000,'x');const ssize_t unused=::write(fd,blob.data(),blob.size());(void)unused;::close(fd);}
    }
    const std::size_t removed=phantom::enforce_log_retention(directory,7,1,(std::uint64_t)::time(nullptr));
    check(removed>0,"size ceiling did not prune any log");
    const std::size_t aged=phantom::enforce_log_retention(directory,0,4096,(std::uint64_t)::time(nullptr)+100000);
    check(aged>0,"retention window did not prune an aged log");
  }
  // ---- structured events ---------------------------------------------------
  {
    const std::string path="/tmp/phantom-events-"+std::to_string((long long)::getpid())+".jsonl";
    int fd=::open(path.c_str(),O_WRONLY|O_CREAT|O_TRUNC|O_CLOEXEC,0600);
    check(fd>=0,"event log fixture");
    phantom::EventLog log;log.open(fd,"build","boot","bundle");
    log.emit_transition(42,"STOPPED","CONTROLLER",2,9,107,7);
    log.flush();::close(fd);
    std::string contents;{FILE* handle=std::fopen(path.c_str(),"rb");if(handle){char buffer[1024];const std::size_t n=std::fread(buffer,1,sizeof(buffer)-1,handle);buffer[n]='\0';contents=buffer;std::fclose(handle);}}
    check(contents.find("\"event\":\"STOPPED\"")!=std::string::npos,"structured event was not written");
    check(contents.find("\"state_before\":2")!=std::string::npos,"state_before missing");
    check(contents.find("\"state_after\":9")!=std::string::npos,"state_after missing");
    check(contents.find("\"fault_code\":107")!=std::string::npos,"fault_code missing");
    check(contents.find("\"subsystem\":\"CONTROLLER\"")!=std::string::npos,"subsystem missing");
    ::unlink(path.c_str());
    check(phantom::EventLog::escape("a\"b\\c\nd")=="a\\\"b\\\\c\\nd","event escaping");
  }
  // ---- runtime-active marker ----------------------------------------------
  {
    const std::string path="/tmp/phantom-marker-"+std::to_string((long long)::getpid());
    {
      phantom::RuntimeActiveMarker first(path);
      check(first.valid(),"marker not created");
      check(!first.previous_run_was_unclean(),"fresh marker reported an unclean previous run");
      // Simulate a crash: the destructor never runs, so the marker survives.
    }
    int fd=::open(path.c_str(),O_WRONLY|O_CREAT,0600);if(fd>=0)::close(fd);
    {
      phantom::RuntimeActiveMarker second(path);
      check(second.previous_run_was_unclean(),"surviving marker was not detected as unclean shutdown");
    }
    ::unlink(path.c_str());
  }
  if(failures){std::cerr<<failures<<" EV3 core checks failed\n";return 1;}
  std::cout<<"EV3 core tests PASS\n";return 0;
}
