#include "phantom/runtime_profile.hpp"
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <sstream>
#include <sys/stat.h>
#include <unistd.h>

namespace phantom { namespace {
bool read_bounded(const std::string& path,std::string& value){std::ifstream stream(path,std::ios::binary);if(!stream)return false;std::ostringstream out;char block[4096];std::size_t total=0;while(stream.read(block,sizeof(block))||stream.gcount()){total+=(std::size_t)stream.gcount();if(total>131072)return false;out.write(block,stream.gcount());}value=out.str();return true;}
bool exactly_once(const std::string&text,const char*token){const auto first=text.find(token);return first!=std::string::npos&&text.find(token,first+1)==std::string::npos;}
}
bool load_runtime_profile(const std::string& config_path,const std::string& bundle_path,RuntimeProfile& profile,std::string& error){
  std::string config,bundle;if(!read_bounded(config_path,config)){error="cannot read runtime config";return false;}if(!read_bounded(bundle_path,bundle)){error="cannot read commissioning bundle";return false;}
  const bool config_diag=exactly_once(config,"\"build_profile\":\"Diagnostic\"");const bool config_qual=exactly_once(config,"\"qualification_only\":true");const bool config_scope0=exactly_once(config,"\"actuator_scope_mask\":0");const bool config_observe0=exactly_once(config,"\"safety_observation_mask\":0");
  const bool bundle_qual=exactly_once(bundle,"\"qualification_only\":true");const bool bundle_scope0=exactly_once(bundle,"\"actuator_scope_mask\":0");const bool bundle_observe0=exactly_once(bundle,"\"safety_observation_mask\":0");
  if(config_diag||config_qual||config_scope0||config_observe0||bundle_qual||bundle_scope0||bundle_observe0){if(!(config_diag&&config_qual&&config_scope0&&config_observe0&&bundle_qual&&bundle_scope0&&bundle_observe0)){error="network-only config/bundle mismatch";return false;}profile.diagnostic=true;profile.qualification_only=true;profile.actuator_scope_mask=0;profile.safety_observation_mask=0;error.clear();return true;}
  if(!exactly_once(config,"\"build_profile\":\"Release\"")||!exactly_once(config,"\"qualification_only\":false")||!exactly_once(config,"\"actuator_scope_mask\":15")||!exactly_once(config,"\"safety_observation_mask\":15")||!exactly_once(bundle,"\"qualification_only\":false")||!exactly_once(bundle,"\"actuator_scope_mask\":15")||!exactly_once(bundle,"\"safety_observation_mask\":15")){error="Release profile contract mismatch";return false;}
  profile=RuntimeProfile{};error.clear();return true;
}
bool publish_controller_boot_id(const std::string& path,std::string& error){
  unsigned char bytes[16];int random_fd=::open("/dev/urandom",O_RDONLY|O_CLOEXEC);if(random_fd<0){error="/dev/urandom unavailable";return false;}std::size_t offset=0;while(offset<sizeof(bytes)){const auto count=::read(random_fd,bytes+offset,sizeof(bytes)-offset);if(count<0&&errno==EINTR)continue;if(count<=0){::close(random_fd);error="CSPRNG read failed";return false;}offset+=(std::size_t)count;}::close(random_fd);
  static const char hex[]="0123456789abcdef";char encoded[33];for(std::size_t i=0;i<16;++i){encoded[2*i]=hex[bytes[i]>>4];encoded[2*i+1]=hex[bytes[i]&15];}encoded[32]='\n';const std::string temporary=path+".tmp";int fd=::open(temporary.c_str(),O_WRONLY|O_CREAT|O_TRUNC|O_CLOEXEC,0644);if(fd<0){error=std::strerror(errno);return false;}bool ok=::fchmod(fd,0644)==0&&::write(fd,encoded,sizeof(encoded))==(ssize_t)sizeof(encoded)&&::fsync(fd)==0;if(::close(fd)!=0)ok=false;if(ok)ok=::rename(temporary.c_str(),path.c_str())==0;if(!ok){::unlink(temporary.c_str());error="boot id atomic write failed";return false;}error.clear();return true;
}
}
