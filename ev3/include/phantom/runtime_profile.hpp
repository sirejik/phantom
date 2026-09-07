#pragma once
#include <cstdint>
#include <string>

namespace phantom {

// Every field here is loaded from the generated runtime configuration and the
// authoritative CommissioningBundle. Nothing in the control path may hard-code a
// value that configuration declares: a knob an operator can edit before HIL must
// actually change behaviour, and a mismatch must fail closed instead of silently
// keeping a compiled-in default.
struct RuntimeProfile {
  bool diagnostic = false;
  bool qualification_only = false;
  std::uint8_t actuator_scope_mask = 0x0f;
  std::uint8_t safety_observation_mask = 0x0f;

  // Commissioning admission (authoritative bundle, not the runtime config).
  bool commissioning_valid = false;
  bool measured_limits_complete = false;
  bool external_power_cut_tested = false;

  // network.*
  std::uint32_t command_timeout_ms = 120;
  std::uint32_t session_stale_ms = 5000;
  std::uint16_t listen_port_udp = 30470;

  // safety.*
  std::uint32_t controller_heartbeat_rate_hz = 20;
  std::uint32_t controller_heartbeat_timeout_ms = 100;
  std::uint32_t loop_safe_hold_ms = 60;
  std::uint32_t loop_fault_ms = 100;

  // logging.*
  std::uint32_t flight_recorder_seconds = 10;
  std::uint32_t flight_recorder_rate_hz = 50;
  std::uint32_t release_retention_days = 7;
  std::uint32_t release_max_mb = 250;

  std::size_t flight_recorder_samples() const {
    return static_cast<std::size_t>(flight_recorder_seconds) * flight_recorder_rate_hz;
  }
  bool network_only() const { return qualification_only && actuator_scope_mask == 0; }
};

bool load_runtime_profile(const std::string& config_path, const std::string& bundle_path,
                          RuntimeProfile& profile, std::string& error);
bool publish_controller_boot_id(const std::string& path, std::string& error);
// Removed on any controller shutdown so the network/mDNS plane cannot keep
// advertising an authority process that no longer exists.
void retire_controller_boot_id(const std::string& path) noexcept;

}  // namespace phantom
