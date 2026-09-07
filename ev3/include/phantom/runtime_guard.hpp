#pragma once
#include <cstdint>
#include <string>
namespace phantom {
std::uint64_t monotonic_us() noexcept;
class HeartbeatChannel {
public:
  // `own_group_gid` is the dedicated liveness group (`phantom-safety-ipc`).
  // Passing (gid_t)-1 leaves ownership untouched for host tests.
  HeartbeatChannel(const std::string& own_path,const std::string& peer_path,std::uint8_t own_role,
                   unsigned own_group_gid=(unsigned)-1) noexcept;
  ~HeartbeatChannel(); bool valid()const noexcept{return fd_>=0;} void send(std::uint64_t now_us)noexcept;
  // Bounded like every other PHANTOM drain: a flooded liveness socket must not
  // be able to stretch the control tick.
  void drain(std::uint64_t now_us)noexcept;
  bool peer_fresh(std::uint64_t now_us,std::uint64_t timeout_us)const noexcept{return last_peer_us_&&now_us>=last_peer_us_&&now_us-last_peer_us_<=timeout_us;}
  std::uint64_t last_peer_us()const noexcept{return last_peer_us_;}
  std::uint64_t dropped()const noexcept{return dropped_;}
private:int fd_=-1;std::string own_,peer_;std::uint8_t role_=0;std::uint64_t sequence_=0,last_peer_us_=0,dropped_=0;
};
class MotorLease {
public:explicit MotorLease(const char*path="/run/phantom/motor-control.lock")noexcept;~MotorLease();bool try_acquire()noexcept;void release()noexcept;bool held()const noexcept{return held_;}
private:int fd_=-1;bool held_=false;
};
}
