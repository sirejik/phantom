#include "phantom/network_ipc.hpp"
#include "phantom/runtime_guard.hpp"
#include <array>
#include <cerrno>
#include <cstring>
#include <iostream>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

namespace {
int failures=0;
void check(bool value,const char*message){if(!value){std::cerr<<"FAIL: "<<message<<"\n";++failures;}}
void put16(unsigned char*p,std::uint16_t v){p[0]=v&255;p[1]=(v>>8)&255;}
void put32(unsigned char*p,std::uint32_t v){for(int i=0;i<4;++i)p[i]=(v>>(8*i))&255;}
void put64(unsigned char*p,std::uint64_t v){for(int i=0;i<8;++i)p[i]=(v>>(8*i))&255;}
std::uint16_t get16(const unsigned char*p){return std::uint16_t(p[0])|std::uint16_t(p[1])<<8;}
bool address(sockaddr_un&out,const std::string&path){if(path.size()>=sizeof(out.sun_path))return false;std::memset(&out,0,sizeof(out));out.sun_family=AF_UNIX;std::memcpy(out.sun_path,path.c_str(),path.size()+1);return true;}
std::array<unsigned char,120> request(std::uint16_t type,const std::array<std::uint8_t,16>&boot,
                                     std::uint64_t generation,unsigned char session_byte,
                                     std::uint64_t sequence,std::uint64_t now){
  std::array<unsigned char,120> value{};put32(value.data(),0x50494850u);put16(value.data()+4,1);put16(value.data()+6,type);std::memcpy(value.data()+12,boot.data(),16);put64(value.data()+28,generation);std::memset(value.data()+36,session_byte,16);value[54]=4;value[56]=127;value[59]=1;value[61]=1;std::memset(value.data()+64,'N',16);put64(value.data()+80,sequence);put64(value.data()+88,now);return value;
}
std::uint16_t exchange(int client,const sockaddr_un&server,phantom::NetworkIpcBoundary&boundary,const std::array<unsigned char,120>&value,std::uint64_t now){
  check(::sendto(client,value.data(),value.size(),0,reinterpret_cast<const sockaddr*>(&server),sizeof(server))==(ssize_t)value.size(),"IPC request send");boundary.drain(now);unsigned char reply[65];const auto n=::recv(client,reply,sizeof(reply),MSG_DONTWAIT);check(n==64,"exact IPC reply length");return n==64?get16(reply+60):0xffff;
}
}

int main(){
  const std::string prefix="/tmp/phantom-ipc-test-"+std::to_string((long long)::getpid()),server_path=prefix+"-server.sock",client_path=prefix+"-client.sock";
  std::array<std::uint8_t,16> boot{};boot.fill(0x42);phantom::NetworkIpcBoundary boundary(server_path,boot,(unsigned)::getuid(),(unsigned)::getgid(),true);check(boundary.valid(),"controller IPC bind");
  int client=::socket(AF_UNIX,SOCK_DGRAM|SOCK_CLOEXEC,0);sockaddr_un own{},server{};check(client>=0&&address(own,client_path)&&address(server,server_path),"client socket setup");::unlink(client_path.c_str());check(::bind(client,reinterpret_cast<sockaddr*>(&own),sizeof(own))==0,"client bind");
  const auto now=phantom::monotonic_us();auto open=request(1,boot,77,0x53,0,now);check(exchange(client,server,boundary,open,now)==0,"session open accepted");check(boundary.session_active(),"session marked active");check(exchange(client,server,boundary,open,now+1)==0,"exact open retry accepted");
  auto competing=request(1,boot,77,0x54,0,now+2);check(exchange(client,server,boundary,competing,now+2)==12,"competing session busy");
  auto command=request(3,boot,77,0x53,1,now+3);std::memset(command.data()+64,0,16);check(exchange(client,server,boundary,command,now+3)==0,"scope-zero command evidence accepted");check(boundary.accepted_commands()==1,"command counted once");check(exchange(client,server,boundary,command,now+4)==3,"duplicate command rejected");check(boundary.accepted_commands()==1,"duplicate had no side effect");
  auto invalid=request(3,boot,77,0x53,2,now+4);std::memset(invalid.data()+64,0,16);put32(invalid.data()+100,0x7fc00000u);check(exchange(client,server,boundary,invalid,now+4)==3,"non-finite command IPC rejected");check(boundary.accepted_commands()==1,"invalid command had no side effect");
  auto invalidate=request(4,boot,77,0x53,0,now+5);std::memset(invalidate.data()+64,0,16);check(exchange(client,server,boundary,invalidate,now+5)==0,"session invalidated");check(!boundary.session_active(),"session inactive");
  auto stale=request(1,boot,78,0x55,0,now-600000);check(exchange(client,server,boundary,stale,now)==3,"stale IPC rejected");
  ::close(client);::unlink(client_path.c_str());if(failures)return 1;std::cout<<"EV3 network IPC tests PASS\n";return 0;
}
