#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "phantom/network_ipc.hpp"
#include "phantom/byte_codec.hpp"
#include "ipc_constants.hpp"
#include "protocol_constants.hpp"
#include <cerrno>
#include <cmath>
#include <cstring>
#include <fcntl.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

namespace phantom { namespace {
namespace layout = ipc;
constexpr std::uint16_t Ok=(std::uint16_t)wire::ResultCode::OK,
                        ErrAuth=(std::uint16_t)wire::ResultCode::ERR_AUTH,
                        ErrSession=(std::uint16_t)wire::ResultCode::ERR_SESSION,
                        ErrBusy=(std::uint16_t)wire::ResultCode::ERR_CONTROL_SESSION_BUSY,
                        ErrUnsupported=(std::uint16_t)wire::ResultCode::ERR_UNSUPPORTED,
                        ErrFormat=(std::uint16_t)wire::ResultCode::ERR_FORMAT;
constexpr std::uint64_t kFreshnessUs=500000;

using bytes::u16;using bytes::u32;using bytes::u64;
using bytes::put16;using bytes::put32;using bytes::put64;using bytes::putf;
bool unix_address(sockaddr_un&out,const std::string&path){if(path.size()>=sizeof(out.sun_path))return false;std::memset(&out,0,sizeof(out));out.sun_family=AF_UNIX;std::memcpy(out.sun_path,path.c_str(),path.size()+1);return true;}
bool all_zero(const unsigned char*p,std::size_t n){for(std::size_t i=0;i<n;++i)if(p[i])return false;return true;}
}

bool read_controller_boot_id(const std::string&path,std::array<std::uint8_t,16>&value) noexcept{
  int fd=::open(path.c_str(),O_RDONLY|O_CLOEXEC);if(fd<0)return false;char text[33];std::size_t n=0;
  while(n<sizeof(text)){const auto got=::read(fd,text+n,sizeof(text)-n);if(got<0&&errno==EINTR)continue;if(got<=0)break;n+=(std::size_t)got;}
  ::close(fd);if(n!=33||text[32]!='\n')return false;
  auto digit=[](char c)->int{if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;return -1;};
  for(std::size_t i=0;i<16;++i){const int hi=digit(text[2*i]),lo=digit(text[2*i+1]);if(hi<0||lo<0)return false;value[i]=(std::uint8_t)((hi<<4)|lo);}
  return !all_zero(value.data(),value.size());
}

NetworkIpcBoundary::NetworkIpcBoundary(const std::string&path,const std::array<std::uint8_t,16>&boot_id,
                                       unsigned expected_uid,unsigned socket_gid,bool network_only,
                                       std::uint32_t session_timeout_ms) noexcept
  :path_(path),boot_id_(boot_id),expected_uid_(expected_uid),network_only_(network_only),
   session_timeout_ms_(session_timeout_ms?session_timeout_ms:5000){
  sockaddr_un address{};if(!unix_address(address,path_))return;
  fd_=::socket(AF_UNIX,SOCK_DGRAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);if(fd_<0)return;
  int enabled=1;if(::setsockopt(fd_,SOL_SOCKET,SO_PASSCRED,&enabled,sizeof(enabled))!=0){::close(fd_);fd_=-1;return;}
  ::unlink(path_.c_str());
  if(::bind(fd_,reinterpret_cast<sockaddr*>(&address),sizeof(address))||::chown(path_.c_str(),(uid_t)-1,(gid_t)socket_gid)||::chmod(path_.c_str(),0660)){::close(fd_);fd_=-1;::unlink(path_.c_str());}
}

NetworkIpcBoundary::~NetworkIpcBoundary(){if(fd_>=0)::close(fd_);if(!path_.empty())::unlink(path_.c_str());}

void NetworkIpcBoundary::end_session() noexcept {
  session_active_=false;last_wire_sequence_=0;session_id_.fill(0);peer_pid_=-1;generation_=0;
}

void NetworkIpcBoundary::expire_stale_session(std::uint64_t now_us) noexcept {
  if(!session_active_)return;
  const std::uint64_t timeout_us=(std::uint64_t)session_timeout_ms_*1000;
  if(last_ipc_us_&&now_us>=last_ipc_us_&&now_us-last_ipc_us_<=timeout_us)return;
  // A lost SESSION_INVALIDATE must never leave a permanently "open" session.
  end_session();
  ++session_expiries_;
}

void NetworkIpcBoundary::drain(std::uint64_t now_us) noexcept{
  if(fd_<0)return;
  for(int count=0;count<16;++count){
    unsigned char request[layout::kControllerRequestBytes];
    sockaddr_un peer{};iovec io{request,sizeof(request)};
    unsigned char control[CMSG_SPACE(sizeof(ucred))];std::memset(control,0,sizeof(control));
    msghdr msg{};msg.msg_name=&peer;msg.msg_namelen=sizeof(peer);msg.msg_iov=&io;msg.msg_iovlen=1;msg.msg_control=control;msg.msg_controllen=sizeof(control);
    const auto received=::recvmsg(fd_,&msg,MSG_DONTWAIT);
    // EINTR consumes budget like any other iteration: the bound is a ceiling on
    // work per 50 Hz tick, and a retry that refunds its slot is not bounded.
    if(received<0){if(errno==EINTR)continue;break;}
    ucred*cred=nullptr;
    for(cmsghdr*c=CMSG_FIRSTHDR(&msg);c;c=CMSG_NXTHDR(&msg,c))
      if(c->cmsg_level==SOL_SOCKET&&c->cmsg_type==SCM_CREDENTIALS&&c->cmsg_len>=CMSG_LEN(sizeof(ucred))){cred=reinterpret_cast<ucred*>(CMSG_DATA(c));break;}
    if(received!=(ssize_t)layout::kControllerRequestBytes||!cred||(unsigned)cred->uid!=expected_uid_){++rejected_requests_;continue;}

    const std::uint16_t type=u16(request+layout::kControllerRequestOffsetRequestType);
    const std::uint64_t generation=u64(request+layout::kControllerRequestOffsetSessionGeneration);
    const std::uint64_t wire_sequence=u64(request+layout::kControllerRequestOffsetWireSequence);
    const std::uint64_t rx_us=u64(request+layout::kControllerRequestOffsetRxMonotonicUs);
    const unsigned char* session=request+layout::kControllerRequestOffsetSessionId;
    const unsigned char* nonce=request+layout::kControllerRequestOffsetClientNonce;
    const unsigned char* command=request+layout::kControllerRequestOffsetCommandPayload;

    // Envelope: magic/version/reserved/boot identity and the canonical-zero
    // reserved bytes the contract mandates for every request type.
    const bool envelope=
      std::memcmp(request+layout::kControllerRequestOffsetMagic,"PHIP",4)==0&&
      u16(request+layout::kControllerRequestOffsetIpcVersion)==layout::kIpcVersion&&
      u32(request+layout::kControllerRequestOffsetReserved0)==0&&
      std::memcmp(request+layout::kControllerRequestOffsetControllerBootId,boot_id_.data(),16)==0&&
      request[layout::kControllerRequestOffsetKeySlot]==0&&
      request[layout::kControllerRequestOffsetRemoteFamily]==4&&
      request[layout::kControllerRequestOffsetReserved1]==0&&
      u16(request+layout::kControllerRequestOffsetReserved2)==0;

    std::uint16_t result=ErrSession;
    bool telemetry_reply=false;
    if(!envelope){result=ErrFormat;}
    else if(!(generation&&rx_us<=now_us&&now_us-rx_us<=kFreshnessUs)){result=ErrSession;}
    else{
      last_ipc_us_=now_us;
      if(type==(std::uint16_t)layout::MessageType::SESSION_OPEN){
        const bool selector=request[layout::kControllerRequestOffsetRole]==0&&
                            !all_zero(session,16)&&wire_sequence==0&&
                            all_zero(command,layout::kControllerRequestSizeCommandPayload);
        if(!network_only_)result=ErrUnsupported;
        else if(!selector)result=ErrAuth;
        else if(session_active_&&peer_pid_==cred->pid&&generation==generation_&&std::memcmp(session,session_id_.data(),16)==0)result=Ok;
        // One CONTROL session at a time. A different peer may only take over
        // when the previous owner process is provably gone; a live owner always
        // wins, so takeover can never be a silent race between two workers.
        else if(session_active_&&(peer_pid_==cred->pid||::kill((pid_t)peer_pid_,0)==0))result=ErrBusy;
        else{session_active_=true;peer_pid_=cred->pid;generation_=generation;last_wire_sequence_=0;std::memcpy(session_id_.data(),session,16);result=Ok;}
      }else if(type==(std::uint16_t)layout::MessageType::COMMAND_SNAPSHOT){
        const std::uint32_t motion=u32(command),tail=u32(command+20);
        float values[4];std::memcpy(values,command+4,sizeof(values));
        bool finite=true;for(float value:values)finite=finite&&std::isfinite(value);
        const bool bounded=values[0]>=-6.4f&&values[0]<=6.4f&&values[1]>=-6.4f&&values[1]<=6.4f&&
                           values[2]>=-6.4f&&values[2]<=6.4f&&values[3]>=0.0f&&values[3]<=1.0f;
        constexpr std::uint32_t mask=wire::kCommandMotionFlagsMotionEnable|wire::kCommandMotionFlagsHoldRequest|wire::kCommandMotionFlagsTrackingValid|wire::kCommandMotionFlagsGraspValid;
        if(!all_zero(nonce,layout::kControllerRequestSizeClientNonce))result=ErrFormat;
        else if(session_active_&&peer_pid_==cred->pid&&generation==generation_&&
                std::memcmp(session,session_id_.data(),16)==0&&wire_sequence>last_wire_sequence_&&
                (motion&~mask)==0&&tail==0&&finite&&bounded){last_wire_sequence_=wire_sequence;++accepted_commands_;result=Ok;}
      }else if(type==(std::uint16_t)layout::MessageType::SESSION_INVALIDATE){
        if(!all_zero(nonce,layout::kControllerRequestSizeClientNonce)||wire_sequence!=0||
           !all_zero(command,layout::kControllerRequestSizeCommandPayload))result=ErrFormat;
        else if(session_active_&&peer_pid_==cred->pid&&generation==generation_&&std::memcmp(session,session_id_.data(),16)==0){end_session();result=Ok;}
      }else if(type==(std::uint16_t)layout::MessageType::TELEMETRY_QUERY){
        if(!all_zero(nonce,layout::kControllerRequestSizeClientNonce)||
           !all_zero(command,layout::kControllerRequestSizeCommandPayload))result=ErrFormat;
        else telemetry_reply=true;
      }else{
        result=ErrUnsupported;
      }
    }
    if(result!=Ok&&!telemetry_reply)++rejected_requests_;

    if(telemetry_reply){
      unsigned char reply[layout::kControllerTelemetrySnapshotBytes]{};
      std::memcpy(reply+layout::kControllerTelemetrySnapshotOffsetMagic,"PHIP",4);
      put16(reply+layout::kControllerTelemetrySnapshotOffsetIpcVersion,layout::kIpcVersion);
      put16(reply+layout::kControllerTelemetrySnapshotOffsetReplyType,(std::uint16_t)layout::MessageType::TELEMETRY_SNAPSHOT);
      std::memcpy(reply+layout::kControllerTelemetrySnapshotOffsetControllerBootId,boot_id_.data(),16);
      put64(reply+layout::kControllerTelemetrySnapshotOffsetSessionGeneration,generation);
      put64(reply+layout::kControllerTelemetrySnapshotOffsetSnapshotMonotonicUs,snapshot_.monotonic_us);
      put16(reply+layout::kControllerTelemetrySnapshotOffsetState,snapshot_.state);
      put16(reply+layout::kControllerTelemetrySnapshotOffsetFaultCode,snapshot_.fault_code);
      put32(reply+layout::kControllerTelemetrySnapshotOffsetStatusFlags,snapshot_.status_flags);
      put16(reply+layout::kControllerTelemetrySnapshotOffsetBatteryMv,snapshot_.battery_mv);
      put16(reply+layout::kControllerTelemetrySnapshotOffsetGripState,snapshot_.grip_state);
      put32(reply+layout::kControllerTelemetrySnapshotOffsetLoopHealthFlags,snapshot_.loop_health_flags);
      std::memcpy(reply+layout::kControllerTelemetrySnapshotOffsetIncidentId,snapshot_.incident_id.data(),16);
      for(std::size_t i=0;i<3;++i){
        putf(reply+layout::kControllerTelemetrySnapshotOffsetQActualRad+4*i,snapshot_.q_actual[i]);
        putf(reply+layout::kControllerTelemetrySnapshotOffsetQSpeedRadS+4*i,snapshot_.q_speed[i]);
      }
      putf(reply+layout::kControllerTelemetrySnapshotOffsetGripActual,snapshot_.grip_actual);
      ::sendto(fd_,reply,sizeof(reply),MSG_DONTWAIT,reinterpret_cast<sockaddr*>(&peer),msg.msg_namelen);
      continue;
    }

    unsigned char reply[layout::kControllerReplyBytes]{};
    std::memcpy(reply+layout::kControllerReplyOffsetMagic,"PHIP",4);
    put16(reply+layout::kControllerReplyOffsetIpcVersion,layout::kIpcVersion);
    put16(reply+layout::kControllerReplyOffsetReplyType,(std::uint16_t)layout::MessageType::REPLY);
    std::memcpy(reply+layout::kControllerReplyOffsetControllerBootId,boot_id_.data(),16);
    put64(reply+layout::kControllerReplyOffsetSessionGeneration,generation);
    std::memcpy(reply+layout::kControllerReplyOffsetSessionId,session,16);
    put64(reply+layout::kControllerReplyOffsetRequestWireSequence,wire_sequence);
    put16(reply+layout::kControllerReplyOffsetResultCode,result);
    ::sendto(fd_,reply,sizeof(reply),MSG_DONTWAIT,reinterpret_cast<sockaddr*>(&peer),msg.msg_namelen);
  }
}

} // namespace phantom
