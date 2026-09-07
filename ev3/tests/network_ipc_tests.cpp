#include "phantom/network_ipc.hpp"
#include "phantom/runtime_guard.hpp"
#include "ipc_constants.hpp"
#include <array>
#include <cerrno>
#include <cstring>
#include <iostream>
#include <string>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

namespace {
namespace layout = phantom::ipc;
int failures=0;
void check(bool value,const char*message){if(!value){std::cerr<<"FAIL: "<<message<<"\n";++failures;}}
void put16(unsigned char*p,std::uint16_t v){p[0]=v&255;p[1]=(v>>8)&255;}
void put32(unsigned char*p,std::uint32_t v){for(int i=0;i<4;++i)p[i]=(v>>(8*i))&255;}
void put64(unsigned char*p,std::uint64_t v){for(int i=0;i<8;++i)p[i]=(v>>(8*i))&255;}
std::uint16_t get16(const unsigned char*p){return std::uint16_t(p[0])|std::uint16_t(p[1])<<8;}
std::uint64_t get64(const unsigned char*p){std::uint64_t v=0;for(int i=7;i>=0;--i)v=(v<<8)|p[i];return v;}
bool address(sockaddr_un&out,const std::string&path){if(path.size()>=sizeof(out.sun_path))return false;std::memset(&out,0,sizeof(out));out.sun_family=AF_UNIX;std::memcpy(out.sun_path,path.c_str(),path.size()+1);return true;}

using Request=std::array<unsigned char,layout::kControllerRequestBytes>;

// Built entirely from generated offsets, so a layout change cannot leave the
// test agreeing with a stale hand-written copy.
Request request(std::uint16_t type,const std::array<std::uint8_t,16>&boot,std::uint64_t generation,
                unsigned char session_byte,std::uint64_t sequence,std::uint64_t now){
  Request value{};
  std::memcpy(value.data()+layout::kControllerRequestOffsetMagic,"PHIP",4);
  put16(value.data()+layout::kControllerRequestOffsetIpcVersion,layout::kIpcVersion);
  put16(value.data()+layout::kControllerRequestOffsetRequestType,type);
  std::memcpy(value.data()+layout::kControllerRequestOffsetControllerBootId,boot.data(),16);
  put64(value.data()+layout::kControllerRequestOffsetSessionGeneration,generation);
  std::memset(value.data()+layout::kControllerRequestOffsetSessionId,session_byte,16);
  value[layout::kControllerRequestOffsetRemoteFamily]=4;
  value[layout::kControllerRequestOffsetRemoteIpv4NetworkOrder]=127;
  value[layout::kControllerRequestOffsetRemoteIpv4NetworkOrder+3]=1;
  value[layout::kControllerRequestOffsetRemotePortNetworkOrder+1]=1;
  put64(value.data()+layout::kControllerRequestOffsetWireSequence,sequence);
  put64(value.data()+layout::kControllerRequestOffsetRxMonotonicUs,now);
  return value;
}

struct Client {
  int fd=-1;sockaddr_un server{};std::string path;
  std::size_t exchange(phantom::NetworkIpcBoundary&boundary,const Request&value,std::uint64_t now,
                       unsigned char*reply,std::size_t reply_capacity){
    check(::sendto(fd,value.data(),value.size(),0,reinterpret_cast<const sockaddr*>(&server),sizeof(server))==(ssize_t)value.size(),"IPC request send");
    boundary.drain(now);
    const auto n=::recv(fd,reply,reply_capacity,MSG_DONTWAIT);
    return n<0?0:(std::size_t)n;
  }
  std::uint16_t result(phantom::NetworkIpcBoundary&boundary,const Request&value,std::uint64_t now){
    unsigned char reply[layout::kControllerTelemetrySnapshotBytes+1];
    const std::size_t n=exchange(boundary,value,now,reply,sizeof(reply));
    check(n==layout::kControllerReplyBytes,"exact IPC reply length");
    if(n!=layout::kControllerReplyBytes)return 0xffff;
    check(get16(reply+layout::kControllerReplyOffsetReplyType)==(std::uint16_t)layout::MessageType::REPLY,"reply type");
    return get16(reply+layout::kControllerReplyOffsetResultCode);
  }
};
}

int main(){
  const std::string prefix="/tmp/phantom-ipc-test-"+std::to_string((long long)::getpid());
  const std::string server_path=prefix+"-server.sock",client_path=prefix+"-client.sock";
  std::array<std::uint8_t,16> boot{};boot.fill(0x42);
  phantom::NetworkIpcBoundary boundary(server_path,boot,(unsigned)::getuid(),(unsigned)::getgid(),true,1000);
  check(boundary.valid(),"controller IPC bind");

  Client client;client.path=client_path;
  client.fd=::socket(AF_UNIX,SOCK_DGRAM|SOCK_CLOEXEC,0);
  sockaddr_un own{};
  check(client.fd>=0&&address(own,client_path)&&address(client.server,server_path),"client socket setup");
  ::unlink(client_path.c_str());
  check(::bind(client.fd,reinterpret_cast<sockaddr*>(&own),sizeof(own))==0,"client bind");

  const std::uint64_t now=phantom::monotonic_us();
  const std::uint16_t kOk=0,kErrAuth=2,kErrSession=3,kErrBusy=12,kErrFormat=1;

  auto open=request((std::uint16_t)layout::MessageType::SESSION_OPEN,boot,77,0x53,0,now);
  check(client.result(boundary,open,now)==kOk,"session open accepted");
  check(boundary.session_active(),"session marked active");
  check(client.result(boundary,open,now+1)==kOk,"exact open retry accepted");

  auto competing=request((std::uint16_t)layout::MessageType::SESSION_OPEN,boot,77,0x54,0,now+2);
  check(client.result(boundary,competing,now+2)==kErrBusy,"competing session busy");

  auto command=request((std::uint16_t)layout::MessageType::COMMAND_SNAPSHOT,boot,77,0x53,1,now+3);
  check(client.result(boundary,command,now+3)==kOk,"scope-zero command evidence accepted");
  check(boundary.accepted_commands()==1,"command counted once");
  check(client.result(boundary,command,now+4)==kErrSession,"duplicate command rejected");
  check(boundary.accepted_commands()==1,"duplicate had no side effect");

  auto non_finite=request((std::uint16_t)layout::MessageType::COMMAND_SNAPSHOT,boot,77,0x53,2,now+4);
  put32(non_finite.data()+layout::kControllerRequestOffsetCommandPayload+4,0x7fc00000u);
  check(client.result(boundary,non_finite,now+4)==kErrSession,"non-finite command IPC rejected");
  check(boundary.accepted_commands()==1,"invalid command had no side effect");

  // Canonical-zero contract (L-09): every request type declares which context
  // fields must be zero, and the controller must enforce all of them.
  auto dirty_nonce=request((std::uint16_t)layout::MessageType::COMMAND_SNAPSHOT,boot,77,0x53,3,now+5);
  dirty_nonce[layout::kControllerRequestOffsetClientNonce]=1;
  check(client.result(boundary,dirty_nonce,now+5)==kErrFormat,"COMMAND_SNAPSHOT accepted a non-zero client nonce");
  auto dirty_reserved=request((std::uint16_t)layout::MessageType::COMMAND_SNAPSHOT,boot,77,0x53,3,now+5);
  dirty_reserved[layout::kControllerRequestOffsetReserved1]=1;
  check(client.result(boundary,dirty_reserved,now+5)==kErrFormat,"non-zero reserved1 accepted");
  auto bad_family=request((std::uint16_t)layout::MessageType::COMMAND_SNAPSHOT,boot,77,0x53,3,now+5);
  bad_family[layout::kControllerRequestOffsetRemoteFamily]=6;
  check(client.result(boundary,bad_family,now+5)==kErrFormat,"non-IPv4 remote family accepted");
  auto dirty_open=request((std::uint16_t)layout::MessageType::SESSION_OPEN,boot,78,0x55,0,now+5);
  dirty_open[layout::kControllerRequestOffsetCommandPayload]=1;
  check(client.result(boundary,dirty_open,now+5)==kErrAuth,"SESSION_OPEN accepted a non-zero command payload");
  auto dirty_invalidate=request((std::uint16_t)layout::MessageType::SESSION_INVALIDATE,boot,77,0x53,4,now+5);
  check(client.result(boundary,dirty_invalidate,now+5)==kErrFormat,"SESSION_INVALIDATE accepted a non-zero wire sequence");
  auto unknown=request(0x00ff,boot,77,0x53,0,now+5);
  check(client.result(boundary,unknown,now+5)==15,"unknown IPC type must be ERR_UNSUPPORTED");

  // Telemetry snapshot (H-01): the controller is the only source of state.
  phantom::TelemetrySnapshot snapshot;
  snapshot.monotonic_us=now+6;snapshot.state=9;snapshot.fault_code=107;snapshot.status_flags=0x18;
  snapshot.battery_mv=7600;snapshot.grip_state=1;snapshot.loop_health_flags=4;
  snapshot.incident_id.fill(0xab);snapshot.q_actual={{1.5f,-2.5f,0.0f}};snapshot.q_speed={{0.25f,0,0}};snapshot.grip_actual=0.5f;
  boundary.publish_snapshot(snapshot);
  auto query=request((std::uint16_t)layout::MessageType::TELEMETRY_QUERY,boot,77,0x53,0,now+6);
  unsigned char reply[layout::kControllerTelemetrySnapshotBytes+1];
  const std::size_t length=client.exchange(boundary,query,now+6,reply,sizeof(reply));
  check(length==layout::kControllerTelemetrySnapshotBytes,"telemetry snapshot length");
  if(length==layout::kControllerTelemetrySnapshotBytes){
    check(std::memcmp(reply+layout::kControllerTelemetrySnapshotOffsetMagic,"PHIP",4)==0,"snapshot magic");
    check(get16(reply+layout::kControllerTelemetrySnapshotOffsetReplyType)==(std::uint16_t)layout::MessageType::TELEMETRY_SNAPSHOT,"snapshot reply type");
    check(get16(reply+layout::kControllerTelemetrySnapshotOffsetState)==9,"snapshot state");
    check(get16(reply+layout::kControllerTelemetrySnapshotOffsetFaultCode)==107,"snapshot fault");
    check(get16(reply+layout::kControllerTelemetrySnapshotOffsetBatteryMv)==7600,"snapshot battery");
    check(get64(reply+layout::kControllerTelemetrySnapshotOffsetSnapshotMonotonicUs)==now+6,"snapshot timestamp");
    float q0=0;std::memcpy(&q0,reply+layout::kControllerTelemetrySnapshotOffsetQActualRad,4);
    check(q0==1.5f,"snapshot q_actual");
    check(std::memcmp(reply+layout::kControllerTelemetrySnapshotOffsetIncidentId,snapshot.incident_id.data(),16)==0,"snapshot incident id");
  }

  auto invalidate=request((std::uint16_t)layout::MessageType::SESSION_INVALIDATE,boot,77,0x53,0,now+7);
  check(client.result(boundary,invalidate,now+7)==kOk,"session invalidated");
  check(!boundary.session_active(),"session inactive");

  auto stale=request((std::uint16_t)layout::MessageType::SESSION_OPEN,boot,78,0x55,0,now-600000);
  check(client.result(boundary,stale,now)==kErrSession,"stale IPC rejected");

  // Session watchdog (M-10): a lost SESSION_INVALIDATE must not leave the
  // controller believing a session is open forever.
  auto reopen=request((std::uint16_t)layout::MessageType::SESSION_OPEN,boot,79,0x56,0,now+8);
  check(client.result(boundary,reopen,now+8)==kOk,"session reopened");
  check(boundary.session_active(),"session reopened active");
  boundary.expire_stale_session(now+8+500000);
  check(boundary.session_active(),"session expired inside its own timeout");
  boundary.expire_stale_session(now+8+2000000);
  check(!boundary.session_active(),"session watchdog did not expire a silent peer");
  check(boundary.session_expiries()==1,"session expiry not counted");

  ::close(client.fd);::unlink(client_path.c_str());
  if(failures)return 1;
  std::cout<<"EV3 network IPC tests PASS\n";return 0;
}
