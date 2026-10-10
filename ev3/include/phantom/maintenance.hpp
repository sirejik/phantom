#pragma once
#include <string>
#include <vector>

#include "phantom/json_reader.hpp"
namespace phantom {
struct CommandResult {
  int code;
  std::string output;
};
CommandResult maintenance_command(const std::vector<std::string>&,
                                  unsigned timeout_seconds = 15);
JsonValue maintenance_json(const std::string&);
std::string maintenance_string(const JsonValue&, const std::string&);
std::string maintenance_quote(const std::string&);
std::string maintenance_serialize(const JsonValue&);
bool maintenance_safe_relative(const std::string&);
bool maintenance_motor_stationary(const std::string& duty_sp,
                                  const std::string& duty,
                                  const std::string& speed,
                                  const std::string& state,
                                  const std::string& stop_action);
std::string maintenance_clock_trust(std::uint64_t epoch_seconds,
                                    bool synchronized);
void maintenance_validate_bundle(const std::string&);
std::string maintenance_digest(const std::string&, bool trim_lf = false);
void maintenance_write(const std::string&, const std::string&);
std::vector<std::string> maintenance_files(const std::string&);
int maintenance_integration(const std::string& build_id);
}  // namespace phantom
