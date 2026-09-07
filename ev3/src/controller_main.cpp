#include "phantom/controller_core.hpp"
#include "phantom/event_log.hpp"
#include "phantom/network_ipc.hpp"
#include "phantom/runtime_guard.hpp"
#include "phantom/runtime_profile.hpp"
#include <algorithm>
#include <array>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <fcntl.h>
#include <grp.h>
#include <iostream>
#include <pwd.h>
#include <string>
#include <sys/stat.h>
#include <thread>
#include <time.h>
#include <unistd.h>
#include <vector>

namespace {
volatile std::sig_atomic_t running=1;
void stop(int){running=0;}

constexpr const char* kBootIdPath="/run/phantom/controller/boot-id";
constexpr const char* kRuntimeMarkerPath="/var/lib/phantom/runtime-active";
constexpr const char* kIncidentDirectory="/var/log/phantom/incidents";

// Incident export is bounded per tick so a frozen ring never competes with the
// control loop for the 20 ms budget.
class IncidentWriter {
public:
  void begin(const std::array<std::uint8_t,16>& id,const phantom::FlightRing& ring) {
    static const char hex[]="0123456789abcdef";
    std::string name;
    for(std::uint8_t byte:id){name.push_back(hex[byte>>4]);name.push_back(hex[byte&15]);}
    ::mkdir("/var/log/phantom",0750);
    ::mkdir(kIncidentDirectory,0750);
    path_=std::string(kIncidentDirectory)+"/"+name+".jsonl";
    fd_=::open(path_.c_str(),O_WRONLY|O_CREAT|O_TRUNC|O_CLOEXEC,0640);
    index_=0;total_=ring.size();active_=fd_>=0;
  }
  bool active() const { return active_; }
  // Returns true once the whole frozen ring has been written.
  bool step(const phantom::FlightRing& ring) {
    if(!active_)return true;
    for(int written=0;written<32&&index_<total_;++written,++index_){
      const phantom::FlightSample& sample=ring.at(index_);
      char line[320];
      const int length=std::snprintf(line,sizeof(line),
        "{\"monotonic_us\":%llu,\"state\":%u,\"fault_code\":%u,\"status_flags\":%u,"
        "\"loop_health_flags\":%u,\"loop_dt_us\":%u,\"command_sequence\":%llu,\"battery_mv\":%u,"
        "\"encoder\":[%d,%d,%d,%d],\"duty_permille\":[%d,%d,%d,%d]}\n",
        (unsigned long long)sample.monotonic_us,(unsigned)sample.state,(unsigned)sample.fault,
        sample.status_flags,sample.loop_health_flags,sample.loop_dt_us,
        (unsigned long long)sample.command_sequence,sample.battery_mv,
        sample.encoder[0],sample.encoder[1],sample.encoder[2],sample.encoder[3],
        sample.duty[0],sample.duty[1],sample.duty[2],sample.duty[3]);
      if(length>0&&::write(fd_,line,(std::size_t)length)!=length){active_=false;break;}
    }
    if(index_>=total_||!active_){if(fd_>=0){::fsync(fd_);::close(fd_);fd_=-1;}active_=false;return true;}
    return false;
  }
private:
  int fd_=-1;std::size_t index_=0,total_=0;bool active_=false;std::string path_;
};
}

int main(int argc,char**argv){
  const bool self_test=argc>1&&std::string(argv[1])=="--self-test";
  if(self_test){
    phantom::RuntimeConfig config;
    phantom::MockMotorBackend backend;phantom::ControllerCore core(backend,config);
    if(!core.initialize()){std::cerr<<"mock backend initialization failed\n";return 1;}
    core.set_safety_heartbeat_alive(true);
    std::vector<std::uint32_t> intervals;intervals.reserve(250);
    auto next=std::chrono::steady_clock::now();std::uint64_t previous=phantom::monotonic_us();
    for(int i=0;i<250;++i){
      next+=std::chrono::milliseconds(20);std::this_thread::sleep_until(next);
      const auto now=phantom::monotonic_us();
      const auto dt=(std::uint32_t)std::min<std::uint64_t>(now-previous,0xffffffffu);
      previous=now;intervals.push_back(dt);core.set_safety_heartbeat_alive(true);core.tick(now,dt);
    }
    std::sort(intervals.begin(),intervals.end());
    const auto p99=intervals[(intervals.size()*99+99)/100-1],maximum=intervals.back();
    backend.set_local_stop(true);core.set_safety_heartbeat_alive(true);core.tick(phantom::monotonic_us(),20000);
    const bool stopped=core.state()==phantom::State::Stopped&&core.stop_latched();
    // The stop latch must survive the physical release; only RESET_STOPPED clears it.
    backend.set_local_stop(false);core.set_safety_heartbeat_alive(true);core.tick(phantom::monotonic_us(),20000);
    const bool latched_after_release=core.state()==phantom::State::Stopped&&core.stop_latched();
    const bool reset_ok=core.request_reset_stopped()==phantom::RecoveryResult::Ok&&!core.stop_latched()&&!core.motion_allowed();
    core.shutdown();
    if(backend.nonzero_writes()!=0||core.motion_allowed()||!stopped||!latched_after_release||!reset_ok||p99>25000||maximum>=50000){
      std::cerr<<"unsafe/timing self-test failure: p99_us="<<p99<<" max_us="<<maximum
               <<" stopped="<<stopped<<" latched_after_release="<<latched_after_release<<" reset_ok="<<reset_ok<<"\n";
      return 1;
    }
    std::cout<<"self-test PASS: latched STOPPED survives release, RESET_STOPPED recovers without arming, motor output zero, p99_us="
             <<p99<<", max_us="<<maximum<<"\n";
    return 0;
  }

  phantom::RuntimeProfile profile;std::string profile_error;
  if(!phantom::load_runtime_profile("/opt/phantom/current/config.generated.json","/opt/phantom/current/commissioning-bundle.generated.json",profile,profile_error)){std::cerr<<"runtime profile: "<<profile_error<<"\n";return 5;}

  phantom::RuntimeConfig config;
  config.command_timeout_ms=profile.command_timeout_ms;
  config.loop_safe_hold_ms=profile.loop_safe_hold_ms;
  config.loop_fault_ms=profile.loop_fault_ms;
  config.heartbeat_timeout_ms=profile.controller_heartbeat_timeout_ms;
  config.flight_recorder_samples=profile.flight_recorder_samples();
  config.qualification_only=profile.qualification_only;
  config.actuator_scope_mask=profile.actuator_scope_mask;
  config.safety_observation_mask=profile.safety_observation_mask;
  config.commissioning_valid=profile.commissioning_valid;
  config.measured_limits_complete=profile.measured_limits_complete;
  config.external_power_cut_tested=profile.external_power_cut_tested;

  phantom::MotorLease lease;if(!lease.try_acquire()){std::cerr<<"motor-control lease unavailable; controller remains stopped\n";return 3;}
  group* safety_group=::getgrnam("phantom-safety-ipc");
  phantom::HeartbeatChannel heartbeat("/run/phantom/safety/controller.sock","/run/phantom/safety/supervisor.sock",1,
                                      safety_group?(unsigned)safety_group->gr_gid:(unsigned)-1);
  if(!heartbeat.valid())return 4;
  heartbeat.send(phantom::monotonic_us());
  std::string boot_error;
  if(!phantom::publish_controller_boot_id(kBootIdPath,boot_error)){std::cerr<<"controller identity: "<<boot_error<<"\n";lease.release();return 6;}
  std::array<std::uint8_t,16> boot_id{};passwd*network_user=::getpwnam("phantom-net");group*ipc_group=::getgrnam("phantom-ipc");
  if(!network_user||!ipc_group||!phantom::read_controller_boot_id(kBootIdPath,boot_id)){std::cerr<<"network IPC identity unavailable\n";phantom::retire_controller_boot_id(kBootIdPath);lease.release();return 7;}

  static const char hex[]="0123456789abcdef";
  std::string boot_hex;for(std::uint8_t byte:boot_id){boot_hex.push_back(hex[byte>>4]);boot_hex.push_back(hex[byte&15]);}
  phantom::EventLog log;log.open(STDOUT_FILENO,"",boot_hex,"");
  phantom::RuntimeActiveMarker marker(kRuntimeMarkerPath);
  if(marker.previous_run_was_unclean())
    log.emit(phantom::monotonic_us(),"UNCLEAN_SHUTDOWN","CONTROLLER",{phantom::EventLog::text("detail","runtime-active marker survived the previous run")});
  ::mkdir("/var/log/phantom",0750);
  phantom::enforce_log_retention(kIncidentDirectory,profile.release_retention_days,profile.release_max_mb,(std::uint64_t)::time(nullptr));

  const bool network_only=profile.network_only();
  phantom::NetworkIpcBoundary network_ipc("/run/phantom/controller/network.sock",boot_id,(unsigned)network_user->pw_uid,(unsigned)ipc_group->gr_gid,network_only,profile.session_stale_ms);
  if(!network_ipc.valid()){std::cerr<<"controller network IPC unavailable\n";phantom::retire_controller_boot_id(kBootIdPath);lease.release();return 8;}
  phantom::Ev3SysfsBackend backend("/sys/class/tacho-motor","/sys/class/lego-sensor",true,profile.actuator_scope_mask,!network_only,!network_only);
  phantom::ControllerCore core(backend,config,&log);
  if(!core.initialize()){std::cerr<<"controller backend: "<<core.initialization_error()<<"\n";phantom::retire_controller_boot_id(kBootIdPath);lease.release();return 2;}

  std::signal(SIGINT,stop);std::signal(SIGTERM,stop);
  IncidentWriter incident;
  auto next=std::chrono::steady_clock::now();std::uint64_t previous=phantom::monotonic_us();
  while(running){
    next+=std::chrono::milliseconds(20);
    const std::uint64_t now=phantom::monotonic_us();
    heartbeat.drain(now);heartbeat.send(now);
    network_ipc.drain(now);network_ipc.expire_stale_session(now);
    core.set_safety_heartbeat_alive(heartbeat.peer_fresh(now,(std::uint64_t)profile.controller_heartbeat_timeout_ms*1000));
    core.set_network_session_active(network_ipc.session_active());
    const auto elapsed=now>=previous?now-previous:(std::uint64_t)profile.loop_fault_ms*1000+1;
    previous=now;
    core.tick(now,(std::uint32_t)std::min<std::uint64_t>(elapsed,0xffffffffu));
    network_ipc.publish_snapshot(core.snapshot());
    // A latched STOPPED keeps the controller alive and observable: it stays in
    // the loop, keeps braking, keeps answering the network plane and waits for
    // an operator RESET_STOPPED. Exiting here would make the documented
    // recovery path unreachable and leave a stale boot id advertised.
    if(core.incident_pending()&&!incident.active()){incident.begin(core.incident_id(),core.recorder());core.clear_incident_pending();}
    if(incident.active())incident.step(core.recorder());
    std::this_thread::sleep_until(next);
  }
  core.shutdown();
  marker.clear();
  phantom::retire_controller_boot_id(kBootIdPath);
  lease.release();
  return 0;
}
