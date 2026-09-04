#include "phantom/controller_core.hpp"
#include "phantom/runtime_guard.hpp"
#include "phantom/runtime_profile.hpp"
#include <algorithm>
#include <chrono>
#include <csignal>
#include <iostream>
#include <vector>
#include <thread>
static volatile std::sig_atomic_t running=1;static void stop(int){running=0;}
int main(int argc,char**argv){
  const bool self_test=argc>1&&std::string(argv[1])=="--self-test";phantom::RuntimeConfig config;config.commissioning_valid=false;config.measured_limits_complete=false;config.external_power_cut_tested=false;
  if(self_test){phantom::MockMotorBackend backend;phantom::ControllerCore core(backend,config);if(!core.initialize()){std::cerr<<"mock backend initialization failed\n";return 1;}core.set_safety_heartbeat_alive(true);std::vector<std::uint32_t> intervals;intervals.reserve(250);auto next=std::chrono::steady_clock::now();std::uint64_t previous=phantom::monotonic_us();for(int i=0;i<250;++i){next+=std::chrono::milliseconds(20);std::this_thread::sleep_until(next);const auto now=phantom::monotonic_us();const auto dt=(std::uint32_t)std::min<std::uint64_t>(now-previous,0xffffffffu);previous=now;intervals.push_back(dt);core.tick(now,dt);}std::sort(intervals.begin(),intervals.end());const auto p99=intervals[(intervals.size()*99+99)/100-1],maximum=intervals.back();backend.set_local_stop(true);core.tick(phantom::monotonic_us(),20000);const bool stopped=core.state()==phantom::State::Stopped;core.shutdown();if(backend.nonzero_writes()!=0||core.motion_allowed()||!stopped||p99>25000||maximum>=50000){std::cerr<<"unsafe/timing self-test failure: p99_us="<<p99<<" max_us="<<maximum<<"\n";return 1;}std::cout<<"self-test PASS: SAFE_HOLD, LOCAL_STOP latched, motor output zero, p99_us="<<p99<<", max_us="<<maximum<<"\n";return 0;}
  phantom::RuntimeProfile profile;std::string profile_error;if(!phantom::load_runtime_profile("/opt/phantom/current/config.generated.json","/opt/phantom/current/commissioning-bundle.generated.json",profile,profile_error)){std::cerr<<"runtime profile: "<<profile_error<<"\n";return 5;}config.qualification_only=profile.qualification_only;config.actuator_scope_mask=profile.actuator_scope_mask;
  phantom::MotorLease lease;if(!lease.try_acquire()){std::cerr<<"motor-control lease unavailable; controller remains stopped\n";return 3;}
  phantom::HeartbeatChannel heartbeat("/run/phantom/controller.sock","/run/phantom/safety.sock",1);if(!heartbeat.valid())return 4;heartbeat.send(phantom::monotonic_us());std::string boot_error;if(!phantom::publish_controller_boot_id("/run/phantom/controller-boot-id",boot_error)){std::cerr<<"controller identity: "<<boot_error<<"\n";lease.release();return 6;}const bool network_only=profile.qualification_only&&profile.actuator_scope_mask==0;phantom::Ev3SysfsBackend backend("/sys/class/tacho-motor","/sys/class/lego-sensor",true,profile.actuator_scope_mask,!network_only,!network_only);phantom::ControllerCore core(backend,config);if(!core.initialize()){std::cerr<<"controller backend: "<<core.initialization_error()<<"\n";lease.release();return 2;}
  std::signal(SIGINT,stop);std::signal(SIGTERM,stop);auto next=std::chrono::steady_clock::now();std::uint64_t previous=phantom::monotonic_us();
  while(running){next+=std::chrono::milliseconds(20);const std::uint64_t now=phantom::monotonic_us();heartbeat.drain(now);heartbeat.send(now);core.set_safety_heartbeat_alive(heartbeat.peer_fresh(now,100000));const auto elapsed=now>=previous?now-previous:100001;previous=now;core.tick(now,(std::uint32_t)std::min<std::uint64_t>(elapsed,0xffffffffu));if(core.state()==phantom::State::Stopped){lease.release();running=0;}std::this_thread::sleep_until(next);}
  core.shutdown();lease.release();return 0;
}
