#include "phantom/runtime_guard.hpp"
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
namespace phantom {
namespace {struct Heartbeat{std::uint32_t magic;std::uint16_t version;std::uint8_t role,reserved;std::uint64_t sequence,sender_us;};constexpr std::uint32_t Magic=0x544e4850u;bool address(sockaddr_un&out,const std::string&path){if(path.size()>=sizeof(out.sun_path))return false;std::memset(&out,0,sizeof(out));out.sun_family=AF_UNIX;std::memcpy(out.sun_path,path.c_str(),path.size()+1);return true;}}
std::uint64_t monotonic_us()noexcept{timespec ts{};if(::clock_gettime(CLOCK_MONOTONIC,&ts))return 0;return std::uint64_t(ts.tv_sec)*1000000u+std::uint64_t(ts.tv_nsec)/1000u;}
HeartbeatChannel::HeartbeatChannel(const std::string&own,const std::string&peer,std::uint8_t role)noexcept:own_(own),peer_(peer),role_(role){sockaddr_un addr{};if(!address(addr,own_))return;fd_=::socket(AF_UNIX,SOCK_DGRAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);if(fd_<0)return;::unlink(own_.c_str());if(::bind(fd_,reinterpret_cast<sockaddr*>(&addr),sizeof(addr))){::close(fd_);fd_=-1;}}
HeartbeatChannel::~HeartbeatChannel(){if(fd_>=0)::close(fd_);if(!own_.empty())::unlink(own_.c_str());}
void HeartbeatChannel::send(std::uint64_t now)noexcept{if(fd_<0)return;sockaddr_un addr{};if(!address(addr,peer_))return;Heartbeat h{Magic,1,role_,0,++sequence_,now};::sendto(fd_,&h,sizeof(h),MSG_DONTWAIT,reinterpret_cast<sockaddr*>(&addr),sizeof(addr));}
void HeartbeatChannel::drain(std::uint64_t now)noexcept{if(fd_<0)return;Heartbeat h{};for(;;){auto n=::recv(fd_,&h,sizeof(h),MSG_DONTWAIT);if(n<0){if(errno==EINTR)continue;break;}if(n==(ssize_t)sizeof(h)&&h.magic==Magic&&h.version==1&&h.role!=role_&&h.reserved==0)last_peer_us_=now;}}
MotorLease::MotorLease(const char*path)noexcept{fd_=::open(path,O_CREAT|O_RDWR|O_CLOEXEC,0640);}MotorLease::~MotorLease(){release();if(fd_>=0)::close(fd_);}bool MotorLease::try_acquire()noexcept{if(held_)return true;if(fd_<0)return false;held_=::flock(fd_,LOCK_EX|LOCK_NB)==0;return held_;}void MotorLease::release()noexcept{if(held_&&fd_>=0)::flock(fd_,LOCK_UN);held_=false;}
}
