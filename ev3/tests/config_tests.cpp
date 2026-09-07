#include "phantom/runtime_profile.hpp"
#include <cstdio>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <unistd.h>

#ifndef PHANTOM_REPO_ROOT
#define PHANTOM_REPO_ROOT "."
#endif

namespace {
int failures=0;
void check(bool value,const char*message){if(!value){std::cerr<<"FAIL: "<<message<<"\n";++failures;}}

std::string read_file(const std::string& path){
  std::ifstream stream(path,std::ios::binary);
  std::ostringstream out;out<<stream.rdbuf();return out.str();
}
std::string write_temp(const std::string& suffix,const std::string& contents){
  const std::string path="/tmp/phantom-config-test-"+std::to_string((long long)::getpid())+"-"+suffix+".json";
  std::ofstream stream(path,std::ios::binary);stream<<contents;stream.close();return path;
}
}

int main(){
  const std::string root=PHANTOM_REPO_ROOT;
  const std::string config_source=read_file(root+"/config/generated/ev3-network-only.generated.json");
  const std::string bundle_source=read_file(root+"/config/generated/commissioning_bundle-network-only.generated.json");
  check(!config_source.empty()&&!bundle_source.empty(),"generated configuration fixtures are readable");

  const std::string config_path=write_temp("config",config_source);
  const std::string bundle_path=write_temp("bundle",bundle_source);

  phantom::RuntimeProfile profile;std::string error;
  check(phantom::load_runtime_profile(config_path,bundle_path,profile,error),("network-only profile must load: "+error).c_str());
  check(profile.diagnostic&&profile.qualification_only,"network-only profile identity");
  check(profile.actuator_scope_mask==0&&profile.safety_observation_mask==0,"network-only scope");
  check(profile.network_only(),"network_only() helper");

  // Every value below is read from configuration, not compiled in (H-04).
  check(profile.command_timeout_ms==120,"command_timeout_ms was not loaded from configuration");
  check(profile.session_stale_ms==5000,"session_stale_ms was not loaded from configuration");
  check(profile.listen_port_udp==30470,"listen_port_udp was not loaded from configuration");
  check(profile.controller_heartbeat_rate_hz==20,"controller_heartbeat_rate_hz was not loaded");
  check(profile.controller_heartbeat_timeout_ms==100,"controller_heartbeat_timeout_ms was not loaded");
  check(profile.loop_safe_hold_ms==60,"loop_safe_hold_ms was not loaded");
  check(profile.loop_fault_ms==100,"loop_fault_ms was not loaded");
  check(profile.flight_recorder_seconds==10&&profile.flight_recorder_rate_hz==50,"flight recorder settings were not loaded");
  check(profile.flight_recorder_samples()==500,"flight recorder depth derives from configuration");
  check(profile.release_retention_days==7&&profile.release_max_mb==250,"retention settings were not loaded");
  // A qualification-only bundle never grants commissioning admission, so READY
  // stays structurally unreachable on this profile.
  check(!profile.commissioning_valid,"qualification-only bundle must not grant commissioning admission");
  check(!profile.external_power_cut_tested,"unqualified POWER_CUT must not be reported as tested");

  // The Release runtime configuration must also satisfy the loader contract.
  const std::string release_config=write_temp("release-config",read_file(root+"/config/generated/ev3.generated.json"));
  const std::string release_bundle=write_temp("release-bundle",read_file(root+"/config/generated/commissioning_bundle.generated.json"));
  phantom::RuntimeProfile release;
  check(phantom::load_runtime_profile(release_config,release_bundle,release,error),("Release profile must load: "+error).c_str());
  check(!release.diagnostic&&!release.qualification_only,"Release profile identity");
  check(release.actuator_scope_mask==15&&release.safety_observation_mask==15,"Release scope");
  check(release.session_stale_ms==5000,"Release session_stale_ms is declared");

  // Fail-closed cases.
  auto expect_rejection=[&](const std::string& mutated_config,const char* message){
    const std::string path=write_temp("mutated",mutated_config);
    phantom::RuntimeProfile rejected;std::string local_error;
    check(!phantom::load_runtime_profile(path,bundle_path,rejected,local_error),message);
    ::unlink(path.c_str());
  };
  std::string broken=config_source;
  const std::size_t safe_hold=broken.find("\"loop_safe_hold_ms\":60");
  check(safe_hold!=std::string::npos,"fixture contains loop_safe_hold_ms");
  expect_rejection(broken.substr(0,safe_hold)+"\"loop_safe_hold_ms\":150"+broken.substr(safe_hold+std::string("\"loop_safe_hold_ms\":60").size()),
                   "loop_safe_hold_ms above loop_fault_ms must be rejected");
  const std::size_t timeout=config_source.find("\"controller_heartbeat_timeout_ms\":100");
  check(timeout!=std::string::npos,"fixture contains controller_heartbeat_timeout_ms");
  expect_rejection(config_source.substr(0,timeout)+"\"controller_heartbeat_timeout_ms\":20"+config_source.substr(timeout+std::string("\"controller_heartbeat_timeout_ms\":100").size()),
                   "heartbeat timeout shorter than one heartbeat period must be rejected");
  const std::size_t scope=config_source.find("\"actuator_scope_mask\":0");
  check(scope!=std::string::npos,"fixture contains actuator_scope_mask");
  expect_rejection(config_source.substr(0,scope)+"\"actuator_scope_mask\":8"+config_source.substr(scope+std::string("\"actuator_scope_mask\":0").size()),
                   "config/bundle scope mismatch must be rejected");
  expect_rejection("{\"build_profile\":\"Diagnostic\"}","incomplete configuration must be rejected");
  expect_rejection("not json","malformed configuration must be rejected");

  ::unlink(config_path.c_str());::unlink(bundle_path.c_str());
  ::unlink(release_config.c_str());::unlink(release_bundle.c_str());
  if(failures)return 1;
  std::cout<<"EV3 runtime configuration tests PASS\n";return 0;
}
