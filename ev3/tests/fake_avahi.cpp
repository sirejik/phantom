#ifdef PHANTOM_FAKE_AVAHI_CLIENT
extern "C" void fake_avahi_dependency();
extern "C" void fake_avahi_client_anchor(){fake_avahi_dependency();}
#else
#include <cstdarg>
#include <cstdint>
#include <string>
#include <vector>
namespace {
using Callback=void(*)(void*,int,void*);
Callback client_callback=nullptr,group_callback=nullptr;
void*client_data=nullptr,*group_data=nullptr;
bool pending=false;int interface_value=0,protocol_value=0,port_value=0,resets=0,commit_result=0;
int client,group,poll;
std::vector<std::string> records;
}
extern "C" {
void fake_avahi_dependency(){}
void* avahi_simple_poll_new(){return &poll;}
const void* avahi_simple_poll_get(void*p){return p;}
int avahi_simple_poll_iterate(void*,int){if(pending){pending=false;group_callback(&group,2,group_data);}return 0;}
void avahi_simple_poll_free(void*){}
void* avahi_client_new(const void*,int,Callback callback,void*data,int*){client_callback=callback;client_data=data;callback(&client,2,data);return &client;}
void avahi_client_free(void*){client_callback=nullptr;group_callback=nullptr;pending=false;}
void* avahi_entry_group_new(void*,Callback callback,void*data){group_callback=callback;group_data=data;callback(&group,0,data);return &group;}
int avahi_entry_group_reset(void*){++resets;pending=false;group_callback(&group,0,group_data);return 0;}
int avahi_entry_group_commit(void*){pending=commit_result==0;return commit_result;}
int avahi_entry_group_add_service(void*,int iface,int proto,int,const char*name,const char*type,const char*domain,const char*,std::uint16_t port,...){
  interface_value=iface;protocol_value=proto;port_value=port;records={name,type,domain};
  va_list args;va_start(args,port);while(const auto*text=va_arg(args,const char*))records.emplace_back(text);va_end(args);return 0;
}
int fake_avahi_interface(){return interface_value;}
int fake_avahi_protocol(){return protocol_value;}
int fake_avahi_port(){return port_value;}
int fake_avahi_resets(){return resets;}
const char*fake_avahi_record(unsigned i){return records.at(i).c_str();}
void fake_avahi_client_state(int state){client_callback(&client,state,client_data);}
void fake_avahi_group_state(int state){pending=false;group_callback(&group,state,group_data);}
void fake_avahi_commit_result(int result){commit_result=result;}
}
#endif
