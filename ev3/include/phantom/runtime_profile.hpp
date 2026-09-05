#pragma once
#include <cstdint>
#include <string>

namespace phantom {
struct RuntimeProfile {
  bool diagnostic=false;
  bool qualification_only=false;
  std::uint8_t actuator_scope_mask=0x0f;
  std::uint8_t safety_observation_mask=0x0f;
};
bool load_runtime_profile(const std::string& config_path,const std::string& bundle_path,RuntimeProfile& profile,std::string& error);
bool publish_controller_boot_id(const std::string& path,std::string& error);
}
