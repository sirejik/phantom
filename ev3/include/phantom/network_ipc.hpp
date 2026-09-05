#pragma once
#include <array>
#include <cstdint>
#include <string>

namespace phantom {

// Fixed-size, versioned controller boundary for the Stage-3 network-only
// profile.  The network process authenticates wire packets; this boundary
// prevents a crash/restart, malformed datagram, or stale generation from
// silently becoming controller authority.
class NetworkIpcBoundary {
public:
  NetworkIpcBoundary(const std::string& path,const std::array<std::uint8_t,16>& boot_id,
                     unsigned expected_uid,unsigned socket_gid,bool network_only) noexcept;
  ~NetworkIpcBoundary();
  bool valid() const noexcept { return fd_>=0; }
  void drain(std::uint64_t now_us) noexcept;
  bool session_active() const noexcept { return session_active_; }
  std::uint64_t accepted_commands() const noexcept { return accepted_commands_; }
private:
  int fd_=-1;
  std::string path_;
  std::array<std::uint8_t,16> boot_id_{};
  unsigned expected_uid_=0;
  bool network_only_=false,session_active_=false;
  int peer_pid_=-1;
  std::uint64_t generation_=0,last_wire_sequence_=0,accepted_commands_=0;
  std::array<std::uint8_t,16> session_id_{};
};

bool read_controller_boot_id(const std::string& path,std::array<std::uint8_t,16>& value) noexcept;

} // namespace phantom
