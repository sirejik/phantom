#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "phantom/network_server.hpp"
#include "phantom/byte_codec.hpp"
#include "ipc_constants.hpp"
#include <algorithm>
#include <chrono>
#include <cstring>
#include <cstdlib>
#include <poll.h>
#include <stdexcept>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>
namespace phantom {
namespace {
sockaddr_un address(const std::string& path){sockaddr_un a{};a.sun_family=AF_UNIX;if(path.size()>=sizeof(a.sun_path))throw std::runtime_error("IPC path too long");std::memcpy(a.sun_path,path.c_str(),path.size()+1);return a;}
constexpr unsigned failure=static_cast<unsigned>(wire::ResultCode::ERR_SESSION);
}
ControllerIpcClient::ControllerIpcClient(const NetworkCrypto& crypto,const std::string& own,const std::string& controller,unsigned uid,unsigned gid)
  :own_(own),controller_(controller),controller_uid_(uid),generation_(bytes::u64(crypto.random_id().data())){
  if(!generation_)generation_=1;
  const auto a=address(own_);address(controller_);
  fd_=::socket(AF_UNIX,SOCK_DGRAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);
  int enabled=1;
  if(fd_<0)throw std::runtime_error("IPC socket unavailable");
  if(::setsockopt(fd_,SOL_SOCKET,SO_PASSCRED,&enabled,sizeof(enabled))){::close(fd_);fd_=-1;throw std::runtime_error("IPC credentials unavailable");}
  ::unlink(own_.c_str());
  if(::bind(fd_,reinterpret_cast<const sockaddr*>(&a),sizeof(a))||::chown(own_.c_str(),-1,gid)||::chmod(own_.c_str(),0660)){
    ::close(fd_);fd_=-1;::unlink(own_.c_str());throw std::runtime_error("IPC bind unavailable");
  }
}
ControllerIpcClient::~ControllerIpcClient(){if(fd_>=0)::close(fd_);::unlink(own_.c_str());}
Buffer ControllerIpcClient::request(unsigned type,const NetworkId& boot,const NetworkId& session,const NetworkId& nonce,const NetworkEndpoint& peer,std::uint64_t sequence,std::uint64_t now,const Buffer& command){
  Buffer r(ipc::kControllerRequestBytes,0);std::memcpy(r.data(),"PHIP",4);bytes::put16(r.data()+ipc::kControllerRequestOffsetIpcVersion,ipc::kIpcVersion);bytes::put16(r.data()+ipc::kControllerRequestOffsetRequestType,type);
  std::copy(boot.begin(),boot.end(),r.begin()+ipc::kControllerRequestOffsetControllerBootId);bytes::put64(r.data()+ipc::kControllerRequestOffsetSessionGeneration,generation_);std::copy(session.begin(),session.end(),r.begin()+ipc::kControllerRequestOffsetSessionId);
  r[ipc::kControllerRequestOffsetRemoteFamily]=4;std::memcpy(r.data()+ipc::kControllerRequestOffsetRemoteIpv4NetworkOrder,&peer.address,4);const auto port=htons(peer.port);std::memcpy(r.data()+ipc::kControllerRequestOffsetRemotePortNetworkOrder,&port,2);
  std::copy(nonce.begin(),nonce.end(),r.begin()+ipc::kControllerRequestOffsetClientNonce);bytes::put64(r.data()+ipc::kControllerRequestOffsetWireSequence,sequence);bytes::put64(r.data()+ipc::kControllerRequestOffsetRxMonotonicUs,now);
  if(!command.empty()){if(command.size()!=24)throw std::runtime_error("IPC command size");std::copy(command.begin(),command.end(),r.begin()+ipc::kControllerRequestOffsetCommandPayload);}return r;
}
bool ControllerIpcClient::exchange(const Buffer& request,Buffer& response,unsigned type,int timeout){
  // Remove delayed replies before issuing another request. Every reply is also
  // bound to boot/generation and, for authorization, session and wire sequence.
  unsigned char discard[256];for(int i=0;i<16;++i)if(::recv(fd_,discard,sizeof(discard),MSG_DONTWAIT)<0)break;
  const auto target=address(controller_);
  if(::sendto(fd_,request.data(),request.size(),MSG_DONTWAIT,reinterpret_cast<const sockaddr*>(&target),sizeof(target))!=static_cast<ssize_t>(request.size()))return false;
  const auto deadline=std::chrono::steady_clock::now()+std::chrono::milliseconds(timeout);
  for(int budget=0;budget<16;++budget){
    const auto remaining=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-std::chrono::steady_clock::now()).count();if(remaining<=0)return false;
    pollfd p{fd_,POLLIN,0};if(::poll(&p,1,static_cast<int>(remaining))<=0)return false;
    unsigned char data[256];alignas(cmsghdr) unsigned char control[CMSG_SPACE(sizeof(ucred))]{};sockaddr_un sender{};iovec io{data,sizeof(data)};
    msghdr m{};m.msg_name=&sender;m.msg_namelen=sizeof(sender);m.msg_iov=&io;m.msg_iovlen=1;m.msg_control=control;m.msg_controllen=sizeof(control);
    const auto n=::recvmsg(fd_,&m,MSG_DONTWAIT);ucred* cred=nullptr;
    for(auto*c=CMSG_FIRSTHDR(&m);c;c=CMSG_NXTHDR(&m,c))if(c->cmsg_level==SOL_SOCKET&&c->cmsg_type==SCM_CREDENTIALS&&c->cmsg_len>=CMSG_LEN(sizeof(ucred)))cred=reinterpret_cast<ucred*>(CMSG_DATA(c));
    const auto size=type==static_cast<unsigned>(ipc::MessageType::REPLY)?ipc::kControllerReplyBytes:ipc::kControllerTelemetrySnapshotBytes;
    if(n!=static_cast<ssize_t>(size)||(m.msg_flags&(MSG_TRUNC|MSG_CTRUNC))||!cred||static_cast<unsigned>(cred->uid)!=controller_uid_||sender.sun_family!=AF_UNIX||std::memcmp(sender.sun_path,target.sun_path,sizeof(sender.sun_path)))continue;
    if(std::memcmp(data,"PHIP",4)||bytes::u16(data+ipc::kControllerReplyOffsetIpcVersion)!=ipc::kIpcVersion||bytes::u16(data+ipc::kControllerReplyOffsetReplyType)!=type||bytes::u32(data+ipc::kControllerReplyOffsetReserved0)||std::memcmp(data+ipc::kControllerReplyOffsetControllerBootId,request.data()+ipc::kControllerRequestOffsetControllerBootId,16)||bytes::u64(data+ipc::kControllerReplyOffsetSessionGeneration)!=generation_)continue;
    if(type==static_cast<unsigned>(ipc::MessageType::REPLY)&&(std::memcmp(data+ipc::kControllerReplyOffsetSessionId,request.data()+ipc::kControllerRequestOffsetSessionId,16)||bytes::u64(data+ipc::kControllerReplyOffsetRequestWireSequence)!=bytes::u64(request.data()+ipc::kControllerRequestOffsetWireSequence)||!bytes::zero(data+ipc::kControllerReplyOffsetReservedTail,2)))continue;
    response.assign(data,data+n);return true;
  }return false;
}
unsigned ControllerIpcClient::open(const NetworkId& boot,const NetworkId& session,const NetworkId& nonce,const NetworkEndpoint& endpoint,std::uint64_t now){Buffer reply;return exchange(request(static_cast<unsigned>(ipc::MessageType::SESSION_OPEN),boot,session,nonce,endpoint,0,now,{}),reply,static_cast<unsigned>(ipc::MessageType::REPLY),250)?bytes::u16(reply.data()+ipc::kControllerReplyOffsetResultCode):failure;}
unsigned ControllerIpcClient::command(const NetworkId& boot,const NetworkId& session,const NetworkEndpoint& endpoint,std::uint64_t seq,std::uint64_t now,const Buffer& payload){Buffer reply;return exchange(request(static_cast<unsigned>(ipc::MessageType::COMMAND_SNAPSHOT),boot,session,{},endpoint,seq,now,payload),reply,static_cast<unsigned>(ipc::MessageType::REPLY),250)?bytes::u16(reply.data()+ipc::kControllerReplyOffsetResultCode):failure;}
void ControllerIpcClient::invalidate(const NetworkId& boot,const NetworkId& session,const NetworkEndpoint& endpoint,std::uint64_t now){Buffer reply;exchange(request(static_cast<unsigned>(ipc::MessageType::SESSION_INVALIDATE),boot,session,{},endpoint,0,now,{}),reply,static_cast<unsigned>(ipc::MessageType::REPLY),250);}
bool ControllerIpcClient::snapshot(const NetworkId& boot,std::uint64_t now,TelemetrySnapshot& out){
  Buffer reply;if(!exchange(request(static_cast<unsigned>(ipc::MessageType::TELEMETRY_QUERY),boot,{},{},{},0,now,{}),reply,static_cast<unsigned>(ipc::MessageType::TELEMETRY_SNAPSHOT),100))return false;
  const auto*p=reply.data();if(!bytes::zero(p+ipc::kControllerTelemetrySnapshotOffsetReservedTail,4))return false;
  out.monotonic_us=bytes::u64(p+ipc::kControllerTelemetrySnapshotOffsetSnapshotMonotonicUs);out.state=bytes::u16(p+ipc::kControllerTelemetrySnapshotOffsetState);out.fault_code=bytes::u16(p+ipc::kControllerTelemetrySnapshotOffsetFaultCode);out.status_flags=bytes::u32(p+ipc::kControllerTelemetrySnapshotOffsetStatusFlags);out.battery_mv=bytes::u16(p+ipc::kControllerTelemetrySnapshotOffsetBatteryMv);out.grip_state=bytes::u16(p+ipc::kControllerTelemetrySnapshotOffsetGripState);out.loop_health_flags=bytes::u32(p+ipc::kControllerTelemetrySnapshotOffsetLoopHealthFlags);
  std::copy(p+ipc::kControllerTelemetrySnapshotOffsetIncidentId,p+ipc::kControllerTelemetrySnapshotOffsetQActualRad,out.incident_id.begin());for(unsigned i=0;i<3;++i){out.q_actual[i]=bytes::f32(p+ipc::kControllerTelemetrySnapshotOffsetQActualRad+i*4);out.q_speed[i]=bytes::f32(p+ipc::kControllerTelemetrySnapshotOffsetQSpeedRadS+i*4);}out.grip_actual=bytes::f32(p+ipc::kControllerTelemetrySnapshotOffsetGripActual);
  return true;
}
void notify_systemd(const std::string& message){
  const auto* path=std::getenv("NOTIFY_SOCKET");if(!path)return;
  std::string value(path);auto a=address(value);if(value[0]=='@')a.sun_path[0]=0;
  const int fd=::socket(AF_UNIX,SOCK_DGRAM|SOCK_CLOEXEC,0);if(fd<0)return;
  ::sendto(fd,message.data(),message.size(),MSG_DONTWAIT,reinterpret_cast<sockaddr*>(&a),offsetof(sockaddr_un,sun_path)+value.size()+(value[0]=='@'?0:1));::close(fd);
}
} // namespace phantom
