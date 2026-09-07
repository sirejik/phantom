#include "phantom/runtime_profile.hpp"
#include "phantom/json_reader.hpp"
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <sstream>
#include <sys/stat.h>
#include <unistd.h>

namespace phantom { namespace {

bool read_bounded(const std::string& path, std::string& value) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) return false;
  std::ostringstream out;
  char block[4096];
  std::size_t total = 0;
  while (stream.read(block, sizeof(block)) || stream.gcount()) {
    total += (std::size_t)stream.gcount();
    if (total > 131072) return false;
    out.write(block, stream.gcount());
  }
  value = out.str();
  return true;
}

bool load_document(const std::string& path, JsonValue& out, std::string& error, const char* label) {
  std::string text;
  if (!read_bounded(path, text)) { error = std::string("cannot read ") + label; return false; }
  std::string parse_error;
  if (!parse_json(text, out, parse_error)) { error = std::string(label) + ": " + parse_error; return false; }
  if (!out.is_object()) { error = std::string(label) + " is not a JSON object"; return false; }
  return true;
}

bool required_uint(const JsonValue& root, const char* path, std::uint64_t min, std::uint64_t max,
                   std::uint32_t& out, std::string& error) {
  std::uint64_t value = 0;
  if (!json_uint(root, path, min, max, value)) {
    error = std::string("configuration field out of contract: ") + path;
    return false;
  }
  out = static_cast<std::uint32_t>(value);
  return true;
}

}  // namespace

bool load_runtime_profile(const std::string& config_path, const std::string& bundle_path,
                          RuntimeProfile& profile, std::string& error) {
  JsonValue config, bundle;
  if (!load_document(config_path, config, error, "runtime config")) return false;
  if (!load_document(bundle_path, bundle, error, "commissioning bundle")) return false;

  std::string build_profile, ready_gate, motor_output_default;
  bool config_qualification = false, bundle_qualification = false;
  std::uint64_t config_scope = 0, config_observe = 0, bundle_scope = 0, bundle_observe = 0;
  if (!json_string(config, "build_profile", build_profile) ||
      !json_bool(config, "qualification_only", config_qualification) ||
      !json_uint(config, "actuator_scope_mask", 0, 15, config_scope) ||
      !json_uint(config, "safety_observation_mask", 0, 15, config_observe) ||
      !json_bool(bundle, "qualification_only", bundle_qualification) ||
      !json_uint(bundle, "actuator_scope_mask", 0, 15, bundle_scope) ||
      !json_uint(bundle, "safety_observation_mask", 0, 15, bundle_observe)) {
    error = "runtime config/bundle identity fields are missing or malformed";
    return false;
  }
  if (build_profile != "Release" && build_profile != "Diagnostic") { error = "unknown build_profile"; return false; }
  // Runtime config and the authoritative bundle must agree exactly; a mismatch is
  // a failed deployment, never a value to pick from.
  if (config_qualification != bundle_qualification || config_scope != bundle_scope ||
      config_observe != bundle_observe) {
    error = "runtime config/bundle qualification mismatch";
    return false;
  }
  if (config_scope & ~config_observe) { error = "actuator scope is not safety-observed"; return false; }
  if (build_profile == "Release" && (config_qualification || config_scope != 15 || config_observe != 15)) {
    error = "Release profile contract mismatch";
    return false;
  }
  if (build_profile == "Diagnostic" && !(config_qualification && config_scope == 0 && config_observe == 0)) {
    error = "Diagnostic profile is not the qualified network-only contract";
    return false;
  }

  profile = RuntimeProfile();
  profile.diagnostic = build_profile == "Diagnostic";
  profile.qualification_only = config_qualification;
  profile.actuator_scope_mask = static_cast<std::uint8_t>(config_scope);
  profile.safety_observation_mask = static_cast<std::uint8_t>(config_observe);

  std::uint32_t listen_port = 0;
  if (!required_uint(config, "network/listen_port_udp", 1024, 65535, listen_port, error) ||
      !required_uint(config, "network/command_timeout_ms", 20, 2000, profile.command_timeout_ms, error) ||
      !required_uint(config, "network/session_stale_ms", 200, 300000, profile.session_stale_ms, error) ||
      !required_uint(config, "safety/controller_heartbeat_rate_hz", 20, 100, profile.controller_heartbeat_rate_hz, error) ||
      !required_uint(config, "safety/controller_heartbeat_timeout_ms", 20, 1000, profile.controller_heartbeat_timeout_ms, error) ||
      !required_uint(config, "safety/loop_safe_hold_ms", 25, 1000, profile.loop_safe_hold_ms, error) ||
      !required_uint(config, "safety/loop_fault_ms", 30, 2000, profile.loop_fault_ms, error) ||
      !required_uint(config, "logging/flight_recorder_seconds", 1, 60, profile.flight_recorder_seconds, error) ||
      !required_uint(config, "logging/flight_recorder_rate_hz", 10, 100, profile.flight_recorder_rate_hz, error) ||
      !required_uint(config, "logging/release_retention_days", 1, 365, profile.release_retention_days, error) ||
      !required_uint(config, "logging/release_max_mb", 1, 4096, profile.release_max_mb, error)) {
    return false;
  }
  profile.listen_port_udp = static_cast<std::uint16_t>(listen_port);

  if (!json_string(config, "safety/motor_output_default", motor_output_default) ||
      motor_output_default != "BRAKE_ZERO") {
    error = "safety.motor_output_default must be BRAKE_ZERO";
    return false;
  }
  if (!json_string(config, "safety/ready_gate", ready_gate)) { error = "safety.ready_gate is missing"; return false; }
  if (profile.loop_safe_hold_ms >= profile.loop_fault_ms) {
    error = "loop_safe_hold_ms must fire strictly before loop_fault_ms";
    return false;
  }
  if (static_cast<std::uint64_t>(profile.controller_heartbeat_timeout_ms) * profile.controller_heartbeat_rate_hz < 1000) {
    error = "controller_heartbeat_timeout_ms is shorter than one heartbeat period";
    return false;
  }

  bool measured_limits_complete = false;
  if (!json_bool(config, "safety/measured_limits_complete", measured_limits_complete)) {
    error = "safety.measured_limits_complete is missing";
    return false;
  }
  profile.measured_limits_complete = measured_limits_complete;

  // Commissioning admission comes only from the authoritative bundle. A
  // qualification-only bundle never grants it, which keeps READY unreachable
  // until a real qualified bundle is installed.
  std::string qualification_status;
  bool external_power_cut_tested = false;
  const JsonValue* power_cut = bundle.path("safety_envelope/external_power_cut_tested");
  if (power_cut && power_cut->kind == JsonValue::Kind::Bool) external_power_cut_tested = power_cut->boolean;
  if (json_string(bundle, "qualification_status", qualification_status)) {
    profile.commissioning_valid = qualification_status == "QUALIFIED" && !bundle_qualification;
  }
  profile.external_power_cut_tested = external_power_cut_tested;
  error.clear();
  return true;
}

bool publish_controller_boot_id(const std::string& path, std::string& error) {
  unsigned char bytes[16];
  int random_fd = ::open("/dev/urandom", O_RDONLY | O_CLOEXEC);
  if (random_fd < 0) { error = "/dev/urandom unavailable"; return false; }
  std::size_t offset = 0;
  while (offset < sizeof(bytes)) {
    const auto count = ::read(random_fd, bytes + offset, sizeof(bytes) - offset);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) { ::close(random_fd); error = "CSPRNG read failed"; return false; }
    offset += (std::size_t)count;
  }
  ::close(random_fd);
  static const char hex[] = "0123456789abcdef";
  char encoded[33];
  for (std::size_t i = 0; i < 16; ++i) { encoded[2 * i] = hex[bytes[i] >> 4]; encoded[2 * i + 1] = hex[bytes[i] & 15]; }
  encoded[32] = '\n';
  const std::string temporary = path + ".tmp";
  int fd = ::open(temporary.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
  if (fd < 0) { error = std::strerror(errno); return false; }
  bool ok = ::fchmod(fd, 0644) == 0 && ::write(fd, encoded, sizeof(encoded)) == (ssize_t)sizeof(encoded) && ::fsync(fd) == 0;
  if (::close(fd) != 0) ok = false;
  if (ok) ok = ::rename(temporary.c_str(), path.c_str()) == 0;
  if (!ok) { ::unlink(temporary.c_str()); error = "boot id atomic write failed"; return false; }
  error.clear();
  return true;
}

void retire_controller_boot_id(const std::string& path) noexcept {
  ::unlink(path.c_str());
  ::unlink((path + ".tmp").c_str());
}

}  // namespace phantom
