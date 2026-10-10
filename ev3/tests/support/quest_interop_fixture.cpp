// Host-only fixture: real network binary and controller IPC, no motor backend.
#include "phantom/network_ipc.hpp"
#include <chrono>
#include <csignal>
#include <fstream>
#include <iostream>
#include <memory>
#include <thread>
#include <vector>
#include <poll.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
namespace {
volatile std::sig_atomic_t running=1;
void stop(int){running=0;}
std::uint64_t now(){return std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();}
struct Fixture {
  std::string directory;
  pid_t child=-1;
  Fixture(){char path[]="/tmp/phantom-quest-interop-XXXXXX";auto p=::mkdtemp(path);if(!p)throw std::runtime_error("mkdtemp failed");directory=p;}
  ~Fixture(){
    if(child>0){::kill(child,SIGTERM);int status=0;bool exited=false;for(int i=0;i<100;++i){if(::waitpid(child,&status,WNOHANG)==child){exited=true;break;}::usleep(10000);}if(!exited){::kill(child,SIGKILL);::waitpid(child,&status,0);}}
    for(auto name:{"control.psk","boot-id","build-manifest.json","network-status.json","network-status.json.tmp","network.sock","controller.sock"})::unlink((directory+"/"+name).c_str());
    ::rmdir(directory.c_str());
  }
  void write(const std::string& name,const std::string& value){std::ofstream f(directory+"/"+name,std::ios::binary);f<<value;if(!f)throw std::runtime_error("fixture file write failed");}
};
}
int main(int argc,char** argv){
  try{
    if(argc!=5)throw std::runtime_error("binary, config, bundle, manifest required");
    ::signal(SIGTERM,stop);::signal(SIGINT,stop);
    Fixture f;
    std::array<std::uint8_t,16> boot{};boot.fill(0x44);
    std::string key;for(int i=0;i<32;++i)key.push_back(static_cast<char>(i));
    f.write("control.psk",key);::chmod((f.directory+"/control.psk").c_str(),0600);
    f.write("boot-id",std::string(32,'4')+"\n");
    f.write("build-manifest.json",argv[4]);
    phantom::NetworkIpcBoundary controller(f.directory+"/controller.sock",boot,::getuid(),::getgid(),true);
    if(!controller.valid())throw std::runtime_error("controller fixture bind failed");
    std::vector<std::string> values{argv[1],"--config",argv[2],"--bundle",argv[3],"--manifest",f.directory+"/build-manifest.json","--control-key",f.directory+"/control.psk","--boot-id",f.directory+"/boot-id","--status",f.directory+"/network-status.json","--bind","0.0.0.0","--ipc-own",f.directory+"/network.sock","--ipc-controller",f.directory+"/controller.sock","--controller-uid",std::to_string(::getuid()),"--ipc-gid",std::to_string(::getgid())};
    std::vector<char*> arguments;for(auto& value:values)arguments.push_back(&value[0]);arguments.push_back(nullptr);
    const auto parent=::getpid();f.child=::fork();if(f.child<0)throw std::runtime_error("fork failed");
    if(f.child==0){::signal(SIGTERM,SIG_DFL);::signal(SIGINT,SIG_DFL);if(::prctl(PR_SET_PDEATHSIG,SIGTERM)||::getppid()!=parent)::_exit(126);::execv(argv[1],arguments.data());::_exit(127);}
    const auto deadline=now()+30000000;
    while(running&&now()<deadline){
      int status=0;if(::waitpid(f.child,&status,WNOHANG)==f.child){f.child=-1;throw std::runtime_error("network fixture child exited");}
      const auto tick=now();phantom::TelemetrySnapshot snapshot;snapshot.monotonic_us=tick;snapshot.state=controller.session_active()?3:2;snapshot.battery_mv=7600;snapshot.status_flags=8;
      controller.publish_snapshot(snapshot);controller.drain(now());
      pollfd input{STDIN_FILENO,POLLIN,0};if(::poll(&input,1,1)>0&&(input.revents&(POLLIN|POLLHUP)))break;
    }
    {std::ifstream status(f.directory+"/network-status.json");std::string value((std::istreambuf_iterator<char>(status)),std::istreambuf_iterator<char>());std::cerr<<"fixture final status: "<<value<<'\n';}
    return 0;
  }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
