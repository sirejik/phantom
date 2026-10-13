#pragma once
#include "phantom/json_reader.hpp"
#include <string>

namespace phantom {
// Canonical session identity for Stage 3. No robot measurements or authority.
const char* network_only_descriptor_json() noexcept;
constexpr const char* kRobotDataPath = "/var/lib/phantom/robot/commissioning.json";
bool load_robot_data(const std::string& path, bool allow_network_only,
                     JsonValue& document, std::string& bytes, std::string& error);
}
