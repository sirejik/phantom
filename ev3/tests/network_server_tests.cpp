#include "phantom/network_server.hpp"
#include "phantom/network_ipc.hpp"
#include "phantom/byte_codec.hpp"
#include "phantom/json_reader.hpp"
#include <atomic>
#include <chrono>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <thread>
#include <sys/stat.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <poll.h>
#include <cstring>
using namespace phantom;
namespace {
void check(bool value,const char* message){if(!value)throw std::runtime_error(message);}
std::uint64_t now_us(){return std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();}
struct Authority:ControllerAuthority{
  bool active=false,available=true;unsigned reject_open=0,reject_command=0;std::uint64_t lag=0,ahead=0;TelemetrySnapshot value{};unsigned commands=0;
  unsigned open(const NetworkId&,const NetworkId&,const NetworkId&,const NetworkEndpoint&,std::uint64_t)override{if(reject_open)return reject_open;active=true;return 0;}
  unsigned command(const NetworkId&,const NetworkId&,const NetworkEndpoint&,std::uint64_t,std::uint64_t,const Buffer&)override{++commands;return reject_command;}
  void invalidate(const NetworkId&,const NetworkId&,const NetworkEndpoint&,std::uint64_t)override{active=false;}
  bool snapshot(const NetworkId&,std::uint64_t now,TelemetrySnapshot& out)override{out=value;out.state=active?3:2;out.monotonic_us=now+ahead-lag;return available;}
};
struct Fixture{
  NetworkCrypto crypto;Buffer key;Authority authority;NetworkConfig config;NetworkId boot{},nonce{};NetworkEndpoint endpoint{htonl(INADDR_LOOPBACK),31337};std::unique_ptr<NetworkServer> server;
  Fixture(unsigned rate=100,unsigned burst=100,NetworkServer::Clock clock={}):key(32){for(unsigned i=0;i<32;++i)key[i]=i;boot.fill('B');nonce.fill('N');config.robot_id="phantom01";config.build_id=std::string(64,'a');parse_hex(wire::kProtocolContractSha256,config.contract_hash.data(),32);config.rate=rate;config.burst=burst;server.reset(new NetworkServer(crypto,config,key,authority,{},clock));server->set_boot(boot,1000000);}
  Buffer packet(wire::MessageType type,const Buffer& payload,std::uint64_t seq=0,NetworkId session={},NetworkId identity={}){NetworkPacket p;p.type=type;p.boot=identity==NetworkId{}?boot:identity;p.session=session;p.sequence=seq;p.sender_us=1;p.payload=payload;return encode_wire(crypto,key,p);}
  Buffer hello_payload(){Buffer p(56,0);std::copy(config.robot_id.begin(),config.robot_id.end(),p.begin());std::copy(nonce.begin(),nonce.end(),p.begin()+36);return p;}
  Buffer send(const Buffer& p,std::uint64_t time=1000000,NetworkEndpoint address={}){return server->process(p.data(),p.size(),address.port?address:endpoint,time);}
  NetworkPacket decode(const Buffer& p){NetworkPacket result;check(!p.empty()&&decode_wire(crypto,key,p.data(),p.size(),result)==DecodeResult::Ok,"reply decode");return result;}
  Buffer hello(){return send(packet(wire::MessageType::HELLO,hello_payload()));}
};
void golden(){NetworkCrypto crypto;JsonValue root;std::string error;check(parse_json(read_bounded_file(std::string(PHANTOM_REPO_ROOT)+"/protocol/golden_vectors/v1.json",4194304),root,error,4194304),"golden JSON");unsigned n=0;for(const auto& v:root.find("vectors")->items){const auto raw=v.find("datagram_hex")->text,keyhex=v.find("hmac_key_hex")->text;Buffer packet(raw.size()/2),key(keyhex.size()/2);check(parse_hex(raw,packet.data(),packet.size())&&parse_hex(keyhex,key.data(),key.size()),"golden hex");NetworkPacket p;check(decode_wire(crypto,key,packet.data(),packet.size(),p)==DecodeResult::Ok,"golden decode");check(encode_wire(crypto,key,p)==packet,"golden exact encode");packet.back()^=1;check(decode_wire(crypto,key,packet.data(),packet.size(),p)==DecodeResult::Authentication,"golden bad HMAC");++n;}check(n==21,"all wire goldens");}
void handshake(){
  Fixture delayed(100,100,[]{return 1000010;});delayed.authority.ahead=10;
  check(!delayed.hello().empty(),"snapshot acquired during IPC is fresh at receipt");
  Fixture future(100,100,[]{return 1000010;});future.authority.ahead=11;
  check(future.hello().empty(),"snapshot later than receipt remains rejected");
  Fixture f;const auto ack=f.hello();auto a=f.decode(ack);check(a.session!=NetworkId{}&&bytes::u16(a.payload.data()+314)==0,"authenticated server session");check(f.hello()==ack,"idempotent HELLO");check(f.server->status_json(1000000).find("\"controller_snapshot_fresh\":true")!=std::string::npos,"current snapshot reported fresh");check(f.server->status_json(1100001).find("\"controller_state\":null")!=std::string::npos,"stale status cannot claim controller health");f.nonce.fill('X');auto rejected=f.decode(f.send(f.packet(wire::MessageType::HELLO,f.hello_payload()),1100000,{htonl(INADDR_LOOPBACK),31338}));check(rejected.session==NetworkId{}&&bytes::u16(rejected.payload.data()+314)==12,"busy session");
  for(unsigned variant=0;variant<4;++variant){Fixture x;auto p=x.hello_payload();if(variant==0)p[0]='x';if(variant==1)p[35]=1;if(variant==2)p[32]=1;if(variant==3)p[52]=1;auto r=x.decode(x.send(x.packet(wire::MessageType::HELLO,p)));check(r.session==NetworkId{}&&bytes::u16(r.payload.data()+314)==(variant==0?3:variant==1?2:15),"semantic HELLO rejection");check(!x.server->session_active(),"rejection session inert");}
}
void session(){Fixture f;const auto id=f.decode(f.hello()).session;Buffer ping(16,0);bytes::put64(ping.data(),7);const auto good=f.packet(wire::MessageType::PING,ping,3,id);auto corrupt=good;corrupt.back()^=1;check(f.send(corrupt,1100000).empty(),"bad HMAC inert");check(f.decode(f.send(good,1200000)).payload==ping,"PONG exact");check(f.send(good,1300000).empty(),"duplicate inert");check(f.send(f.packet(wire::MessageType::PING,ping,2,id),1400000).empty(),"reorder inert");check(f.send(f.packet(wire::MessageType::PING,ping,4,id),1500000,{htonl(INADDR_LOOPBACK),31338}).empty(),"endpoint bound");NetworkId wrong{};wrong.fill('Z');check(f.send(f.packet(wire::MessageType::PING,ping,4,id,wrong),1600000).empty(),"boot bound");
  Buffer command(24,0);bytes::put32(command.data(),5);bytes::putf(command.data()+4,.1f);bytes::putf(command.data()+16,.4f);f.send(f.packet(wire::MessageType::COMMAND,command,4,id),1700000);check(f.authority.commands==1&&f.server->count("motor_write_attempts_rejected")==1,"zero-scope command recorded");f.authority.value.fault_code=107;f.authority.value.battery_mv=7123;f.authority.value.incident_id.fill(0xab);auto t=f.decode(f.server->telemetry(1710000));check(bytes::u16(t.payload.data()+130)==107&&bytes::u16(t.payload.data()+194)==7123&&t.payload[136]==0xab&&bytes::u64(t.payload.data()+152)==4,"controller telemetry");
  f.authority.available=false;check(f.server->telemetry(1800000).empty(),"missing snapshot suppresses telemetry");f.server->stop(1900000);check(f.hello().empty(),"missing snapshot suppresses HELLO");f.authority.available=true;f.authority.lag=100001;check(f.hello().empty(),"stale snapshot suppresses HELLO");
  f.authority.lag=0;auto new_id=f.decode(f.hello()).session;f.server->set_boot(wrong,2000000);check(!f.server->session_active()&&!f.authority.active,"restart invalidates");check(f.send(f.packet(wire::MessageType::COMMAND,command,5,new_id),2100000).empty(),"old boot command inert");
  Fixture expired;auto old=expired.decode(expired.hello()).session;expired.server->expire(6000001);check(!expired.server->session_active(),"timeout expiry");check(expired.send(expired.packet(wire::MessageType::COMMAND,command,1,old),6100000).empty(),"expired command inert");
  Fixture blocked;blocked.authority.reject_open=12;check(blocked.decode(blocked.hello()).session==NetworkId{},"IPC open gates session");blocked.authority.reject_open=0;auto bid=blocked.decode(blocked.hello()).session;blocked.authority.reject_command=3;blocked.send(blocked.packet(wire::MessageType::COMMAND,command,1,bid),1100000);check(!blocked.server->session_active(),"IPC command rejection invalidates");
}
void malformed(){Fixture f;const auto hello=f.packet(wire::MessageType::HELLO,f.hello_payload());for(unsigned offset:{0u,4u,6u,10u,12u}){auto bad=hello;bad[offset]=0xff;check(f.send(bad).empty(),"cheap malformed header");}for(auto size:{10u,151u,153u,1025u}){Buffer bad(size,0);check(f.send(bad).empty(),"invalid packet size");}auto unknown=f.hello_payload();unknown[34]=1;check(f.send(f.packet(wire::MessageType::HELLO,unknown)).empty()&&f.server->count("hmac_fail")==0,"unknown slot pre-HMAC");
  Buffer c(24,0);auto id=f.decode(f.hello()).session;auto raw=f.packet(wire::MessageType::COMMAND,c,1,id);for(const auto bits:{0x7fc00000u,0x7f800000u}){bytes::put32(raw.data()+68,bits);auto digest=f.crypto.hmac(f.key,raw.data(),raw.size()-32);std::copy(digest.begin(),digest.end(),raw.end()-32);check(f.send(raw,1100000).empty(),"authenticated nonfinite inert");}check(f.authority.commands==0,"no malformed command forwarded");
  Fixture flood(1,2);auto h=flood.packet(wire::MessageType::HELLO,flood.hello_payload());for(unsigned i=0;i<1000;++i)flood.send(h);check(flood.server->count("rx_drop")==998,"bounded flood");
}
void keys(){const auto path="/tmp/phantom-key-test-"+std::to_string(getpid());for(const auto edge:{9,10,13,32}){Buffer key(32,1);key.front()=key.back()=edge;{std::ofstream out(path,std::ios::binary);out.write(reinterpret_cast<const char*>(key.data()),key.size());}::chmod(path.c_str(),0600);check(read_control_key(path)==key,"raw whitespace preserved");}::chmod(path.c_str(),0644);bool rejected=false;try{read_control_key(path);}catch(...){rejected=true;}check(rejected,"world-readable key rejected");::unlink(path.c_str());}
void systemd_notification(){const auto name="@phantom-notify-test-"+std::to_string(getpid());const int fd=::socket(AF_UNIX,SOCK_DGRAM,0);check(fd>=0,"notify socket");sockaddr_un a{};a.sun_family=AF_UNIX;std::memcpy(a.sun_path+1,name.data()+1,name.size()-1);check(!::bind(fd,reinterpret_cast<sockaddr*>(&a),offsetof(sockaddr_un,sun_path)+name.size()),"abstract notify bind");::setenv("NOTIFY_SOCKET",name.c_str(),1);notify_systemd("READY=1");::unsetenv("NOTIFY_SOCKET");pollfd p{fd,POLLIN,0};const bool ready=::poll(&p,1,100)>0;char data[32]{};const auto n=ready?::recv(fd,data,sizeof(data),0):0;::close(fd);check(n==7&&std::string(data,n)=="READY=1","abstract systemd readiness");}
void real_ipc(){NetworkCrypto crypto;NetworkId boot{},session{},nonce{};boot.fill(1);session.fill(2);nonce.fill(3);const auto base="/tmp/phantom-native-ipc-"+std::to_string(getpid());NetworkIpcBoundary boundary(base+".ctrl",boot,getuid(),getgid(),true);check(boundary.valid(),"real boundary bind");std::atomic<bool> stop{false};std::thread controller([&]{while(!stop){TelemetrySnapshot s;s.monotonic_us=now_us();s.state=2;s.battery_mv=7123;boundary.publish_snapshot(s);boundary.drain(s.monotonic_us);std::this_thread::sleep_for(std::chrono::milliseconds(1));}});
  bool pass=false;try{ControllerIpcClient client(crypto,base+".net",base+".ctrl",getuid(),getgid());TelemetrySnapshot out;check(client.snapshot(boot,now_us(),out)&&out.battery_mv==7123,"real SCM_CREDENTIALS snapshot");NetworkEndpoint peer{htonl(INADDR_LOOPBACK),31337};check(client.open(boot,session,nonce,peer,now_us())==0,"real IPC open");Buffer command(24,0);check(client.command(boot,session,peer,1,now_us(),command)==0,"real IPC command");check(client.command(boot,session,peer,1,now_us(),command)!=0,"real IPC replay rejected");client.invalidate(boot,session,peer,now_us());ControllerIpcClient wrong(crypto,base+".wrong",base+".ctrl",getuid()+1,getgid());check(!wrong.snapshot(boot,now_us(),out),"wrong response credentials rejected");pass=true;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';}stop=true;controller.join();check(pass,"native IPC suite");}
}
int main(){try{golden();handshake();session();malformed();keys();real_ipc();systemd_notification();std::cout<<"native network tests PASS: 21 golden vectors, sessions, failures, bounds, keys, real IPC, readiness\n";return 0;}catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<'\n';return 1;}}
