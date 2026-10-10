// Exercise the actual publisher against a fake external Avahi ABI, rather
// than recreating its publication logic. Fake libraries are never installed.
#define main phantom_mdns_main
#include "../src/mdns_main.cpp"
#undef main
#include <cstring>
namespace {
void check(bool value,const char*message){if(!value)throw std::runtime_error(message);}
}
int main(){
  void*library=::dlopen("libavahi-common.so.3",RTLD_NOW|RTLD_LOCAL);
  try{
    check(library!=nullptr,"fake Avahi loaded");
    auto protocol=symbol<int(*)()>(library,"fake_avahi_protocol");
    auto interface_value=symbol<int(*)()>(library,"fake_avahi_interface");
    auto port=symbol<int(*)()>(library,"fake_avahi_port");
    auto resets=symbol<int(*)()>(library,"fake_avahi_resets");
    auto record=symbol<const char*(*)(unsigned)>(library,"fake_avahi_record");
    auto client_state=symbol<void(*)(int)>(library,"fake_avahi_client_state");
    auto group_state=symbol<void(*)(int)>(library,"fake_avahi_group_state");
    auto commit_result=symbol<void(*)(int)>(library,"fake_avahi_commit_result");
    phantom::NetworkConfig config;config.robot_id="phantom01";config.build_id=std::string(64,'a');
    phantom::NetworkId boot{};boot.fill(1);
    {
      Publisher p(config);p.iterate();check(port()==0,"no publication without boot");p.update(boot);p.iterate();
      check(protocol()==0&&interface_value()==-1&&port()==30470,"IPv4 on all interfaces");
      check(std::string(record(0))=="PHANTOM-phantom01"&&std::string(record(1))=="_phantom-ev3._udp"&&std::string(record(2))=="local.","service identity");
      check(std::string(record(5))=="controller_boot_id="+phantom::hex(boot.data(),boot.size()),"boot TXT");p.iterate();
      boot.fill(2);p.update(boot);p.iterate();check(resets()==1&&std::string(record(5))=="controller_boot_id="+phantom::hex(boot.data(),boot.size()),"restart republishes new boot");
      p.update({});p.iterate();check(resets()==2,"missing boot withdraws publication");
      p.update(boot);p.iterate();client_state(1);p.iterate();check(resets()==3,"daemon registration withdraws service");
      client_state(2);p.iterate();group_state(3);bool rejected=false;try{p.iterate();}catch(...){rejected=true;}check(rejected,"collision fails closed");
    }
    {
      Publisher p(config);p.update(boot);commit_result(-1);bool rejected=false;try{p.iterate();}catch(...){rejected=true;}check(rejected,"failed registration is not readiness");commit_result(0);
    }
    {
      Publisher p(config);client_state(100);bool rejected=false;try{p.iterate();}catch(...){rejected=true;}check(rejected,"daemon failure propagates");
    }
    ::dlclose(library);std::cout<<"mDNS adapter tests PASS: IPv4, identity, restart, withdrawal, failures\n";return 0;
  }catch(const std::exception&e){if(library)::dlclose(library);std::cerr<<"FAIL: "<<e.what()<<'\n';return 1;}
}
