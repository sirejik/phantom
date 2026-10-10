#pragma once
#include "phantom/controller_core.hpp"
#include <array>
#include <cstdint>
#include <string>
#include <sys/un.h>

namespace phantom {

// Fixed-size, versioned controller boundary.  The network process
// authenticates wire packets; this boundary prevents a crash/restart, malformed
// datagram, or stale generation from silently becoming controller authority,
// and it is the only path by which controller state leaves the controller.
//
// Byte offsets and lengths come from protocol/generated/ipc_constants.hpp,
// which is generated from config/shared/protocol/ipc-schema.json together with the Python
// layout module and the shared golden vectors.
class NetworkIpcBoundary {
public:
  NetworkIpcBoundary(const std::string& path,const std::array<std::uint8_t,16>& boot_id,
                     unsigned expected_uid,unsigned socket_gid,bool network_only,
                     std::uint32_t session_timeout_ms=5000) noexcept;
  ~NetworkIpcBoundary();
  bool valid() const noexcept { return fd_>=0; }
  void drain(std::uint64_t now_us) noexcept;
  // Expires a session whose SESSION_INVALIDATE was lost (§7.2.2 watchdog).
  void expire_stale_session(std::uint64_t now_us) noexcept;
  void publish_snapshot(const TelemetrySnapshot& snapshot) noexcept { snapshot_=snapshot; }
  bool session_active() const noexcept { return session_active_; }
  std::uint64_t accepted_commands() const noexcept { return accepted_commands_; }
  std::uint64_t rejected_requests() const noexcept { return rejected_requests_; }
  std::uint64_t session_expiries() const noexcept { return session_expiries_; }

private:
  void end_session() noexcept;

  int fd_=-1;
  std::string path_;
  std::array<std::uint8_t,16> boot_id_{};
  unsigned expected_uid_=0;
  bool network_only_=false,session_active_=false;
  int peer_pid_=-1;
  std::uint32_t session_timeout_ms_=5000;
  std::uint64_t generation_=0,last_wire_sequence_=0,accepted_commands_=0;
  std::uint64_t last_ipc_us_=0,rejected_requests_=0,session_expiries_=0;
  std::array<std::uint8_t,16> session_id_{};
  TelemetrySnapshot snapshot_;
};

bool read_controller_boot_id(const std::string& path,std::array<std::uint8_t,16>& value) noexcept;

}  // namespace phantom
