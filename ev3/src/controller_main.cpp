#include "phantom/controller_core.hpp"
#include "phantom/runtime_guard.hpp"
#include <algorithm>
#include <chrono>
#include <csignal>
#include <iostream>
#include <thread>
static volatile std::sig_atomic_t running=1;static void stop(int){running=0;}
int main(int argc,char**argv){
  const bool self_test=argc>1&&std::string(argv[1])=="--self-test";phantom::RuntimeConfig config;config.commissioning_valid=false;config.measured_limits_complete=false;config.external_power_cut_tested=false;
  if(self_test){phantom::MockMotorBackend backend;phantom::ControllerCore core(backend,config);core.initialize();core.set_safety_heartbeat_alive(true);core.tick(1000000,20000);core.shutdown();if(backend.nonzero_writes()!=0){std::cerr<<"unsafe motor output\n";return 1;}std::cout<<"self-test PASS: READY blocked, motor output zero\n";return 0;}
  phantom::MotorLease lease;if(!lease.try_acquire()){std::cerr<<"motor-control lease unavailable; controller remains stopped\n";return 3;}
  phantom::HeartbeatChannel heartbeat("/run/phantom/controller.sock","/run/phantom/safety.sock",1);if(!heartbeat.valid())return 4;heartbeat.send(phantom::monotonic_us());phantom::Ev3SysfsBackend backend;phantom::ControllerCore core(backend,config);core.initialize();
  std::signal(SIGINT,stop);std::signal(SIGTERM,stop);auto next=std::chrono::steady_clock::now();std::uint64_t previous=phantom::monotonic_us();
  while(running){next+=std::chrono::milliseconds(20);const std::uint64_t now=phantom::monotonic_us();heartbeat.drain(now);heartbeat.send(now);core.set_safety_heartbeat_alive(heartbeat.peer_fresh(now,100000));const auto elapsed=now>=previous?now-previous:100001;previous=now;core.tick(now,(std::uint32_t)std::min<std::uint64_t>(elapsed,0xffffffffu));if(core.state()==phantom::State::Stopped){lease.release();running=0;}std::this_thread::sleep_until(next);}
  core.shutdown();lease.release();return 0;
}
