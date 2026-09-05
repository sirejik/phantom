#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "phantom/network_ipc.hpp"
#include "protocol_constants.hpp"
#include <cerrno>
#include <cmath>
#include <cstring>
#include <fcntl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

namespace phantom { namespace {
constexpr std::uint32_t Magic=0x50494850u; // "PHIP" on little-endian Linux
constexpr std::uint16_t Version=1,Open=1,OpenReply=2,Command=3,Invalidate=4;
constexpr std::uint16_t Ok=(std::uint16_t)wire::ResultCode::OK,ErrAuth=(std::uint16_t)wire::ResultCode::ERR_AUTH,ErrSession=(std::uint16_t)wire::ResultCode::ERR_SESSION,ErrBusy=(std::uint16_t)wire::ResultCode::ERR_CONTROL_SESSION_BUSY,ErrUnsupported=(std::uint16_t)wire::ResultCode::ERR_UNSUPPORTED;
constexpr std::size_t RequestBytes=120,ReplyBytes=64;
std::uint16_t u16(const unsigned char*p){return std::uint16_t(p[0])|std::uint16_t(p[1])<<8;}
std::uint32_t u32(const unsigned char*p){return std::uint32_t(p[0])|std::uint32_t(p[1])<<8|std::uint32_t(p[2])<<16|std::uint32_t(p[3])<<24;}
std::uint64_t u64(const unsigned char*p){std::uint64_t v=0;for(int i=7;i>=0;--i)v=(v<<8)|p[i];return v;}
void put16(unsigned char*p,std::uint16_t v){p[0]=v&255;p[1]=(v>>8)&255;}
void put32(unsigned char*p,std::uint32_t v){for(int i=0;i<4;++i)p[i]=(v>>(8*i))&255;}
void put64(unsigned char*p,std::uint64_t v){for(int i=0;i<8;++i)p[i]=(v>>(8*i))&255;}
bool unix_address(sockaddr_un&out,const std::string&path){if(path.size()>=sizeof(out.sun_path))return false;std::memset(&out,0,sizeof(out));out.sun_family=AF_UNIX;std::memcpy(out.sun_path,path.c_str(),path.size()+1);return true;}
bool all_zero(const unsigned char*p,std::size_t n){for(std::size_t i=0;i<n;++i)if(p[i])return false;return true;}
}

bool read_controller_boot_id(const std::string&path,std::array<std::uint8_t,16>&value) noexcept{
  int fd=::open(path.c_str(),O_RDONLY|O_CLOEXEC);if(fd<0)return false;char text[33];std::size_t n=0;while(n<sizeof(text)){const auto got=::read(fd,text+n,sizeof(text)-n);if(got<0&&errno==EINTR)continue;if(got<=0)break;n+=(std::size_t)got;}::close(fd);if(n!=33||text[32]!='\n')return false;
  auto digit=[](char c)->int{if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;return -1;};
  for(std::size_t i=0;i<16;++i){const int hi=digit(text[2*i]),lo=digit(text[2*i+1]);if(hi<0||lo<0)return false;value[i]=(std::uint8_t)((hi<<4)|lo);}return !all_zero(value.data(),value.size());
}

NetworkIpcBoundary::NetworkIpcBoundary(const std::string&path,const std::array<std::uint8_t,16>&boot_id,unsigned expected_uid,unsigned socket_gid,bool network_only) noexcept:path_(path),boot_id_(boot_id),expected_uid_(expected_uid),network_only_(network_only){
  sockaddr_un address{};if(!unix_address(address,path_))return;fd_=::socket(AF_UNIX,SOCK_DGRAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);if(fd_<0)return;int enabled=1;if(::setsockopt(fd_,SOL_SOCKET,SO_PASSCRED,&enabled,sizeof(enabled))!=0){::close(fd_);fd_=-1;return;}::unlink(path_.c_str());if(::bind(fd_,reinterpret_cast<sockaddr*>(&address),sizeof(address))||::chown(path_.c_str(),(uid_t)-1,(gid_t)socket_gid)||::chmod(path_.c_str(),0660)){::close(fd_);fd_=-1;::unlink(path_.c_str());}
}
NetworkIpcBoundary::~NetworkIpcBoundary(){if(fd_>=0)::close(fd_);if(!path_.empty())::unlink(path_.c_str());}

void NetworkIpcBoundary::drain(std::uint64_t now_us) noexcept{
  if(fd_<0)return;
  for(int count=0;count<16;++count){
    unsigned char request[RequestBytes];sockaddr_un peer{};iovec io{request,sizeof(request)};unsigned char control[CMSG_SPACE(sizeof(ucred))];std::memset(control,0,sizeof(control));msghdr msg{};msg.msg_name=&peer;msg.msg_namelen=sizeof(peer);msg.msg_iov=&io;msg.msg_iovlen=1;msg.msg_control=control;msg.msg_controllen=sizeof(control);
    const auto received=::recvmsg(fd_,&msg,MSG_DONTWAIT);if(received<0){if(errno==EINTR){--count;continue;}break;}
    ucred*cred=nullptr;for(cmsghdr*c=CMSG_FIRSTHDR(&msg);c;c=CMSG_NXTHDR(&msg,c))if(c->cmsg_level==SOL_SOCKET&&c->cmsg_type==SCM_CREDENTIALS&&c->cmsg_len>=CMSG_LEN(sizeof(ucred))){cred=reinterpret_cast<ucred*>(CMSG_DATA(c));break;}
    if(received!=(ssize_t)RequestBytes||!cred||(unsigned)cred->uid!=expected_uid_)continue;
    const bool envelope=u32(request)==Magic&&u16(request+4)==Version&&u32(request+8)==0&&std::memcmp(request+12,boot_id_.data(),16)==0&&request[53]==0&&request[55]==0&&u16(request+62)==0;
    const std::uint16_t type=u16(request+6);const std::uint64_t generation=u64(request+28),wire_sequence=u64(request+80),rx_us=u64(request+88);std::uint16_t result=ErrSession;
    if(envelope&&generation&&rx_us<=now_us&&now_us-rx_us<=500000){
      if(type==Open){
        const bool selector=request[52]==0&&request[53]==0&&request[54]==4&&!all_zero(request+36,16)&&wire_sequence==0;
        if(!network_only_)result=ErrUnsupported;
        else if(!selector)result=ErrAuth;
        else if(session_active_&&peer_pid_==cred->pid&&generation==generation_&&std::memcmp(request+36,session_id_.data(),16)==0)result=Ok;
        else if(session_active_&&peer_pid_==cred->pid)result=ErrBusy;
        else{session_active_=true;peer_pid_=cred->pid;generation_=generation;last_wire_sequence_=0;std::memcpy(session_id_.data(),request+36,16);result=Ok;}
      }else if(type==Command){
        const std::uint32_t motion=u32(request+96),tail=u32(request+116);float values[4];std::memcpy(values,request+100,sizeof(values));bool finite=true;for(float value:values)finite=finite&&std::isfinite(value);const bool bounded=values[0]>=-6.4f&&values[0]<=6.4f&&values[1]>=-6.4f&&values[1]<=6.4f&&values[2]>=-6.4f&&values[2]<=6.4f&&values[3]>=0.0f&&values[3]<=1.0f;
        constexpr std::uint32_t mask=wire::kCommandMotionFlagsMotionEnable|wire::kCommandMotionFlagsHoldRequest|wire::kCommandMotionFlagsTrackingValid|wire::kCommandMotionFlagsGraspValid;if(session_active_&&peer_pid_==cred->pid&&generation==generation_&&std::memcmp(request+36,session_id_.data(),16)==0&&wire_sequence>last_wire_sequence_&&(motion&~mask)==0&&tail==0&&finite&&bounded){last_wire_sequence_=wire_sequence;++accepted_commands_;result=Ok;}
      }else if(type==Invalidate){
        if(session_active_&&peer_pid_==cred->pid&&generation==generation_&&std::memcmp(request+36,session_id_.data(),16)==0){session_active_=false;last_wire_sequence_=0;session_id_.fill(0);result=Ok;}
      }
    }
    unsigned char reply[ReplyBytes]{};put32(reply,Magic);put16(reply+4,Version);put16(reply+6,OpenReply);std::memcpy(reply+12,boot_id_.data(),16);put64(reply+28,generation);std::memcpy(reply+36,request+36,16);put64(reply+52,wire_sequence);put16(reply+60,result);
    ::sendto(fd_,reply,sizeof(reply),MSG_DONTWAIT,reinterpret_cast<sockaddr*>(&peer),msg.msg_namelen);
  }
}
} // namespace phantom
