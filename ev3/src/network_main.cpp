#include "phantom/network_server.hpp"
#include "phantom/network_ipc.hpp"
#include <chrono>
#include <arpa/inet.h>
#include <csignal>
#include <cstdio>
#include <fstream>
#include <grp.h>
#include <iostream>
#include <map>
#include <poll.h>
#include <pwd.h>
#include <stdexcept>
#include <sys/socket.h>
#include <unistd.h>
namespace {
volatile std::sig_atomic_t stopping=0;
void stop(int){stopping=1;}
std::uint64_t now_us(){return std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();}
void status(const std::string& path,const std::string& data){std::ofstream f(path+".tmp",std::ios::trunc);f<<data;f.close();if(!f||::rename((path+".tmp").c_str(),path.c_str()))throw std::runtime_error("status write failed");}
}
int main(int argc,char**argv){
  std::map<std::string,std::string> args{{"--config","/opt/phantom/current/config.generated.json"},{"--bundle",""},{"--manifest","/opt/phantom/current/build-manifest.json"},{"--control-key","/var/lib/phantom/secrets/control.psk"},{"--boot-id","/run/phantom/controller/boot-id"},{"--status","/run/phantom/network/status.json"},{"--ipc-own","/run/phantom/network/controller.sock"},{"--ipc-controller","/run/phantom/controller/network.sock"},{"--bind","0.0.0.0"},{"--controller-uid",""},{"--ipc-gid",""}};
  int fd=-1;
  try{
    for(int i=1;i<argc;i+=2){if(!args.count(argv[i])||i+1>=argc)throw std::runtime_error("unknown or missing network argument");args[argv[i]]=argv[i+1];}
    unsigned uid,gid;
    if(args["--controller-uid"].empty()){auto*p=::getpwnam("phantom-ctrl");if(!p)throw std::runtime_error("controller account missing");uid=p->pw_uid;}else uid=std::stoul(args["--controller-uid"]);
    if(args["--ipc-gid"].empty()){auto*g=::getgrnam("phantom-ipc");if(!g)throw std::runtime_error("IPC group missing");gid=g->gr_gid;}else gid=std::stoul(args["--ipc-gid"]);
    phantom::NetworkCrypto crypto;auto config=phantom::load_network_config(crypto,args["--config"],args["--bundle"],args["--manifest"]);
    phantom::ControllerIpcClient authority(crypto,args["--ipc-own"],args["--ipc-controller"],uid,gid);
    phantom::NetworkServer server(crypto,config,phantom::read_control_key(args["--control-key"]),authority,[](const std::string& event){std::cout<<"{\"event\":\""<<event<<"\"}"<<std::endl;},now_us);
    std::signal(SIGTERM,stop);std::signal(SIGINT,stop);
    phantom::NetworkId boot{};while(!stopping&&!phantom::read_controller_boot_id(args["--boot-id"],boot))::poll(nullptr,0,50);
    if(stopping)return 0;
    server.set_boot(boot,now_us());
    fd=::socket(AF_INET,SOCK_DGRAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);if(fd<0)throw std::runtime_error("UDP socket unavailable");
    sockaddr_in a{};a.sin_family=AF_INET;a.sin_port=htons(config.port);if(::inet_pton(AF_INET,args["--bind"].c_str(),&a.sin_addr)!=1||::bind(fd,reinterpret_cast<sockaddr*>(&a),sizeof(a)))throw std::runtime_error("UDP bind failed");
    std::cout<<"{\"event\":\"NETWORK_READY\",\"port\":"<<config.port<<"}"<<std::endl;
    phantom::notify_systemd("READY=1\nSTATUS=UDP listener active");
    std::uint64_t identity_due=0,telemetry_due=0,status_due=0;bool identity_valid=true;
    while(!stopping){
      auto now=now_us();if(now>=identity_due){identity_valid=phantom::read_controller_boot_id(args["--boot-id"],boot);if(identity_valid)server.set_boot(boot,now);else server.stop(now);identity_due=now+250000;}
      pollfd p{fd,POLLIN,0};::poll(&p,1,10);
      for(int i=0;i<32&&(p.revents&POLLIN);++i){unsigned char data[1025];sockaddr_in peer{};socklen_t n=sizeof(peer);const auto got=::recvfrom(fd,data,sizeof(data),MSG_DONTWAIT,reinterpret_cast<sockaddr*>(&peer),&n);if(got<0)break;
        if(!identity_valid)continue;
        now=now_us();phantom::NetworkEndpoint endpoint{peer.sin_addr.s_addr,ntohs(peer.sin_port)};const auto reply=server.process(data,got,endpoint,now);if(!reply.empty())::sendto(fd,reply.data(),reply.size(),MSG_DONTWAIT,reinterpret_cast<sockaddr*>(&peer),sizeof(peer));
      }
      now=now_us();server.expire(now);
      if(identity_valid&&now>=telemetry_due){auto data=server.telemetry(now);if(!data.empty()){auto e=server.endpoint();sockaddr_in peer{};peer.sin_family=AF_INET;peer.sin_addr.s_addr=e.address;peer.sin_port=htons(e.port);::sendto(fd,data.data(),data.size(),MSG_DONTWAIT,reinterpret_cast<sockaddr*>(&peer),sizeof(peer));}telemetry_due=now+50000;}
      if(now>=status_due){status(args["--status"],server.status_json(now_us()));status_due=now+1000000;}
    }
    server.stop(now_us());status(args["--status"],server.status_json(now_us()));::close(fd);return 0;
  }catch(const std::exception&){if(fd>=0)::close(fd);std::cerr<<"{\"event\":\"NETWORK_STARTUP_OR_RUNTIME_FAILED\"}"<<std::endl;return 1;}
}
