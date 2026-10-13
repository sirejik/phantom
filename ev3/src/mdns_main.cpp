#include "phantom/network_server.hpp"
#include "phantom/network_ipc.hpp"
#include <cerrno>
#include <chrono>
#include <csignal>
#include <dlfcn.h>
#include <iostream>
#include <map>
#include <stdexcept>
namespace {
volatile std::sig_atomic_t stopping=0;
void stop(int){stopping=1;}
// Stable opaque C ABI from avahi-client/client.h, publish.h and
// avahi-common/simple-watch.h. Cross headers are supplied by ev3/docker/Dockerfile;
// runtime symbols remain loaded explicitly for fail-closed dependency checks.
// Publication uses Avahi over D-Bus; there is no custom mDNS implementation.
struct AvahiClient;struct AvahiEntryGroup;struct AvahiSimplePoll;struct AvahiPoll;
constexpr int ClientRunning=2,ClientFailure=100,GroupEstablished=2,
              GroupCollision=3,GroupFailure=4,ProtocolIpv4=0,InterfaceAny=-1;
template<class T>T symbol(void* library,const char* name){auto p=reinterpret_cast<T>(::dlsym(library,name));if(!p)throw std::runtime_error("Avahi API unavailable");return p;}
class Publisher {
public:
  explicit Publisher(const phantom::NetworkConfig& config):config_(config){
    try{
      common_=::dlopen("libavahi-common.so.3",RTLD_NOW|RTLD_LOCAL);
      library_=::dlopen("libavahi-client.so.3",RTLD_NOW|RTLD_LOCAL);
      if(!common_||!library_)throw std::runtime_error("Avahi libraries unavailable");
      poll_new_=symbol<decltype(poll_new_)>(common_,"avahi_simple_poll_new");
      poll_get_=symbol<decltype(poll_get_)>(common_,"avahi_simple_poll_get");
      poll_iterate_=symbol<decltype(poll_iterate_)>(common_,"avahi_simple_poll_iterate");
      poll_free_=symbol<decltype(poll_free_)>(common_,"avahi_simple_poll_free");
      client_new_=symbol<decltype(client_new_)>(library_,"avahi_client_new");
      client_free_=symbol<decltype(client_free_)>(library_,"avahi_client_free");
      group_new_=symbol<decltype(group_new_)>(library_,"avahi_entry_group_new");
      group_reset_=symbol<decltype(group_reset_)>(library_,"avahi_entry_group_reset");
      group_commit_=symbol<decltype(group_commit_)>(library_,"avahi_entry_group_commit");
      add_service_=symbol<decltype(add_service_)>(library_,"avahi_entry_group_add_service");
      poll_=poll_new_();if(!poll_)throw std::runtime_error("Avahi poll unavailable");
      int error=0;client_=client_new_(poll_get_(poll_),0,client_event,this,&error);
      if(!client_)throw std::runtime_error("Avahi daemon unavailable");
    }catch(...){cleanup();throw;}
  }
  ~Publisher(){cleanup();}
  Publisher(const Publisher&)=delete;Publisher&operator=(const Publisher&)=delete;
  void update(const phantom::NetworkId& boot){if(boot!=boot_){withdraw();boot_=boot;}}
  void iterate(){
    if(poll_iterate_(poll_,250)<0&&errno!=EINTR)throw std::runtime_error("Avahi poll failed");
    if(client_state_==ClientFailure||group_state_==GroupCollision||group_state_==GroupFailure)throw std::runtime_error("Avahi publication failed");
    if(client_state_!=ClientRunning){withdraw();return;}
    if(boot_==phantom::NetworkId{})return;
    if(!submitted_){
      if(!group_)group_=group_new_(client_,group_event,this);
      if(!group_)throw std::runtime_error("Avahi group unavailable");
      const auto name="PHANTOM-"+config_.robot_id,robot="robot_id="+config_.robot_id,
        boot="controller_boot_id="+phantom::hex(boot_.data(),boot_.size()),build="build_id="+config_.build_id;
      if(add_service_(group_,InterfaceAny,ProtocolIpv4,0,name.c_str(),"_phantom-ev3._udp","local.",nullptr,static_cast<std::uint16_t>(config_.port),robot.c_str(),"protocol_major=1",boot.c_str(),build.c_str(),static_cast<const char*>(nullptr))<0||group_commit_(group_)<0)throw std::runtime_error("Avahi registration failed");
      submitted_=true;submitted_at_=std::chrono::steady_clock::now();
    }
    if(group_state_==GroupEstablished&&!announced_){
      announced_=true;std::cout<<"{\"event\":\"DNS_SD_PUBLISHED\"}"<<std::endl;
      phantom::notify_systemd("READY=1\nSTATUS=DNS-SD service published");
    }
    if(!announced_&&std::chrono::steady_clock::now()-submitted_at_>std::chrono::seconds(20))throw std::runtime_error("Avahi publication timeout");
  }
private:
  static void client_event(AvahiClient*,int state,void* data){static_cast<Publisher*>(data)->client_state_=state;}
  static void group_event(AvahiEntryGroup*,int state,void* data){static_cast<Publisher*>(data)->group_state_=state;}
  void withdraw(){if(group_&&submitted_&&group_reset_(group_)<0)throw std::runtime_error("Avahi withdrawal failed");submitted_=announced_=false;group_state_=0;}
  void cleanup(){if(client_&&client_free_)client_free_(client_);if(poll_&&poll_free_)poll_free_(poll_);if(library_)::dlclose(library_);if(common_)::dlclose(common_);client_=nullptr;poll_=nullptr;library_=common_=nullptr;}
  phantom::NetworkConfig config_;phantom::NetworkId boot_{};
  void*common_=nullptr,*library_=nullptr;AvahiSimplePoll*poll_=nullptr;AvahiClient*client_=nullptr;AvahiEntryGroup*group_=nullptr;
  int client_state_=0,group_state_=0;bool submitted_=false,announced_=false;
  std::chrono::steady_clock::time_point submitted_at_{};
  AvahiSimplePoll*(*poll_new_)()=nullptr;
  const AvahiPoll*(*poll_get_)(AvahiSimplePoll*)=nullptr;
  int(*poll_iterate_)(AvahiSimplePoll*,int)=nullptr;
  void(*poll_free_)(AvahiSimplePoll*)=nullptr;
  AvahiClient*(*client_new_)(const AvahiPoll*,int,void(*)(AvahiClient*,int,void*),void*,int*)=nullptr;
  void(*client_free_)(AvahiClient*)=nullptr;
  AvahiEntryGroup*(*group_new_)(AvahiClient*,void(*)(AvahiEntryGroup*,int,void*),void*)=nullptr;
  int(*group_reset_)(AvahiEntryGroup*)=nullptr;
  int(*group_commit_)(AvahiEntryGroup*)=nullptr;
  int(*add_service_)(AvahiEntryGroup*,int,int,int,const char*,const char*,const char*,const char*,std::uint16_t,...)=nullptr;
};
}
int main(int argc,char**argv){
  std::map<std::string,std::string> args{{"--config","/opt/phantom/current/config.generated.json"},{"--bundle",""},{"--manifest","/opt/phantom/current/build-manifest.json"},{"--boot-id","/run/phantom/controller/boot-id"}};
  try{
    for(int i=1;i<argc;i+=2){if(!args.count(argv[i])||i+1>=argc)throw std::runtime_error("invalid mDNS argument");args[argv[i]]=argv[i+1];}
    phantom::NetworkCrypto crypto;const auto c=phantom::load_network_config(crypto,args["--config"],args["--bundle"],args["--manifest"]);
    std::signal(SIGTERM,stop);std::signal(SIGINT,stop);Publisher publisher(c);
    while(!stopping){phantom::NetworkId boot{};if(!phantom::read_controller_boot_id(args["--boot-id"],boot))boot.fill(0);publisher.update(boot);publisher.iterate();}
    return 0;
  }catch(const std::exception&){std::cerr<<"{\"event\":\"DNS_SD_PUBLICATION_FAILED\"}"<<std::endl;return 1;}
}
