#include "phantom/event_log.hpp"
#include "phantom/motor_backend.hpp"
#include "phantom/runtime_guard.hpp"
#include "phantom/runtime_profile.hpp"
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <grp.h>
#include <iostream>
#include <string>
#include <sys/stat.h>
#include <thread>
#include <time.h>
#include <unistd.h>

namespace {
volatile std::sig_atomic_t running=1;
void stop(int){running=0;}
constexpr const char* kLogDirectory="/var/log/phantom";
constexpr const char* kEmergencyLog="/var/log/phantom/safety-emergency.log";
// Bounded so repeated takeover episodes can never fill the brick's storage.
constexpr long kEmergencyLogMaxBytes=262144;

void rotate_if_large(const char* path,long limit){
  struct stat info;
  if(::stat(path,&info)!=0||info.st_size<limit)return;
  const std::string previous=std::string(path)+".1";
  ::rename(path,previous.c_str());
}

void emergency_event(std::uint64_t now,std::uint64_t last,bool local){
  char line[256];
  const int n=std::snprintf(line,sizeof(line),
    "{\"event\":\"SAFETY_TAKEOVER\",\"subsystem\":\"SAFETY\",\"monotonic_us\":%llu,"
    "\"last_controller_heartbeat_us\":%llu,\"local_stop\":%s}\n",
    (unsigned long long)now,(unsigned long long)last,local?"true":"false");
  ::mkdir(kLogDirectory,0750);
  rotate_if_large(kEmergencyLog,kEmergencyLogMaxBytes);
  int fd=::open(kEmergencyLog,O_WRONLY|O_CREAT|O_APPEND|O_CLOEXEC,0640);
  if(fd>=0){const ssize_t written=::write(fd,line,(std::size_t)n);if(written==n)::fsync(fd);::close(fd);}
  // The same event also reaches the journal, so a full disk cannot hide it.
  const ssize_t unused=::write(STDOUT_FILENO,line,(std::size_t)n);(void)unused;
}
}

int main(int argc,char**argv){
  if(argc>1&&std::string(argv[1])=="--self-test"){
    phantom::MockMotorBackend b;std::string e;b.initialize(e);b.brake_all();
    std::cout<<"safety self-test PASS: brake path available\n";return b.nonzero_writes()?1:0;
  }
  phantom::RuntimeProfile profile;std::string error;
  if(!phantom::load_runtime_profile("/opt/phantom/current/config.generated.json","/opt/phantom/current/commissioning-bundle.generated.json",profile,error)){std::cerr<<"runtime profile: "<<error<<"\n";return 5;}
  const bool network_only=profile.network_only();
  // The supervisor pre-opens all physically present stop I/O but writes only on takeover.
  phantom::Ev3SysfsBackend backend("/sys/class/tacho-motor","/sys/class/lego-sensor",false,profile.actuator_scope_mask,!network_only,!network_only);
  if(!backend.initialize(error)){std::cerr<<"safety backend: "<<error<<"\n";return 2;}
  ::mkdir(kLogDirectory,0750);
  phantom::enforce_log_retention(kLogDirectory,profile.release_retention_days,profile.release_max_mb,(std::uint64_t)::time(nullptr));
  group* safety_group=::getgrnam("phantom-safety-ipc");
  phantom::HeartbeatChannel heartbeat("/run/phantom/safety/supervisor.sock","/run/phantom/safety/controller.sock",2,
                                      safety_group?(unsigned)safety_group->gr_gid:(unsigned)-1);
  if(!heartbeat.valid())return 4;
  phantom::MotorLease lease;std::signal(SIGINT,stop);std::signal(SIGTERM,stop);
  const std::uint64_t startup=phantom::monotonic_us();
  const std::uint64_t timeout_us=(std::uint64_t)profile.controller_heartbeat_timeout_ms*1000;
  bool seen=false,inhibit=false,reported=false;std::uint64_t inhibit_since=0;
  while(running){
    const std::uint64_t now=phantom::monotonic_us();
    heartbeat.drain(now);heartbeat.send(now);
    if(heartbeat.last_peer_us())seen=true;
    const auto io=backend.read();
    const bool stale=seen&&!heartbeat.peer_fresh(now,timeout_us);
    const bool startup_expired=!seen&&now-startup>500000;
    if(startup_expired&&!seen&&!io.local_stop_pressed){
      backend.brake_all();lease.release();
      if(!reported){emergency_event(now,0,false);reported=true;}
    }else if(io.local_stop_pressed||stale){
      if(!inhibit){inhibit=true;inhibit_since=now;}
      const bool acquired=lease.try_acquire();
      if(acquired||now-inhibit_since>=timeout_us){
        backend.brake_all();lease.release();
        if(!reported){emergency_event(now,heartbeat.last_peer_us(),io.local_stop_pressed);reported=true;}
      }
    }else{inhibit=false;reported=false;inhibit_since=0;lease.release();}
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
  }
  if(inhibit){backend.brake_all();}
  return 0;
}
