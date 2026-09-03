#include "phantom/motor_backend.hpp"
#include "phantom/runtime_guard.hpp"
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <thread>
#include <unistd.h>
static volatile std::sig_atomic_t running=1;static void stop(int){running=0;}
static void emergency_event(std::uint64_t now,std::uint64_t last,bool local){char line[256];const int n=std::snprintf(line,sizeof(line),"{\"event\":\"SAFETY_TAKEOVER\",\"monotonic_us\":%llu,\"last_controller_heartbeat_us\":%llu,\"local_stop\":%s}\n",(unsigned long long)now,(unsigned long long)last,local?"true":"false");int fd=::open("/var/log/phantom/safety-emergency.log",O_WRONLY|O_CREAT|O_APPEND|O_CLOEXEC,0640);if(fd>=0){const ssize_t written=::write(fd,line,(std::size_t)n);if(written==n)::fsync(fd);::close(fd);}}
int main(int argc,char**argv){
  if(argc>1&&std::string(argv[1])=="--self-test"){phantom::MockMotorBackend b;std::string e;b.initialize(e);b.brake_all();std::cout<<"safety self-test PASS: brake path available\n";return b.nonzero_writes()?1:0;}
  // The supervisor pre-opens I/O but does not write motor sysfs until takeover.
  phantom::Ev3SysfsBackend backend("/sys/class/tacho-motor","/sys/class/lego-sensor",false);std::string error;if(!backend.initialize(error)){std::cerr<<"safety backend: "<<error<<"\n";return 2;}
  phantom::HeartbeatChannel heartbeat("/run/phantom/safety.sock","/run/phantom/controller.sock",2);if(!heartbeat.valid())return 4;phantom::MotorLease lease;std::signal(SIGINT,stop);std::signal(SIGTERM,stop);
  const std::uint64_t startup=phantom::monotonic_us();bool seen=false,inhibit=false,reported=false;std::uint64_t inhibit_since=0;
  while(running){const std::uint64_t now=phantom::monotonic_us();heartbeat.drain(now);heartbeat.send(now);if(heartbeat.last_peer_us())seen=true;const auto io=backend.read();const bool stale=seen&&!heartbeat.peer_fresh(now,100000);const bool startup_expired=!seen&&now-startup>500000;
    if(io.local_stop_pressed||stale||startup_expired){if(!inhibit){inhibit=true;inhibit_since=now;}const bool acquired=lease.try_acquire();if(acquired||now-inhibit_since>=100000){backend.brake_all();if(!reported){emergency_event(now,heartbeat.last_peer_us(),io.local_stop_pressed);reported=true;}}}
    std::this_thread::sleep_for(std::chrono::milliseconds(20));}
  if(inhibit){backend.brake_all();}return 0;
}
