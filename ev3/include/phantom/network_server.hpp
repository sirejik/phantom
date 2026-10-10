#pragma once
#include "phantom/network_wire.hpp"
#include "phantom/controller_core.hpp"
#include <functional>
#include <map>
#include <netinet/in.h>
namespace phantom {
struct NetworkEndpoint {
  std::uint32_t address=0;std::uint16_t port=0;
  bool operator==(const NetworkEndpoint& b)const{return address==b.address&&port==b.port;}
};
struct NetworkConfig {
  std::string robot_id,build_id;Digest bundle_hash{},contract_hash{};
  unsigned port=30470,rate=100,burst=100,retry_ms=5000,stale_ms=5000;
};
NetworkConfig load_network_config(const NetworkCrypto&,const std::string&,const std::string&,const std::string&);
class ControllerAuthority {
public:
  virtual ~ControllerAuthority()=default;
  virtual unsigned open(const NetworkId&,const NetworkId&,const NetworkId&,const NetworkEndpoint&,std::uint64_t)=0;
  virtual unsigned command(const NetworkId&,const NetworkId&,const NetworkEndpoint&,std::uint64_t,std::uint64_t,const Buffer&)=0;
  virtual void invalidate(const NetworkId&,const NetworkId&,const NetworkEndpoint&,std::uint64_t)=0;
  virtual bool snapshot(const NetworkId&,std::uint64_t,TelemetrySnapshot&)=0;
};
class ControllerIpcClient final:public ControllerAuthority {
public:
  ControllerIpcClient(const NetworkCrypto&,const std::string&,const std::string&,unsigned,unsigned);
  ~ControllerIpcClient();
  unsigned open(const NetworkId&,const NetworkId&,const NetworkId&,const NetworkEndpoint&,std::uint64_t) override;
  unsigned command(const NetworkId&,const NetworkId&,const NetworkEndpoint&,std::uint64_t,std::uint64_t,const Buffer&) override;
  void invalidate(const NetworkId&,const NetworkId&,const NetworkEndpoint&,std::uint64_t) override;
  bool snapshot(const NetworkId&,std::uint64_t,TelemetrySnapshot&) override;
private:
  Buffer request(unsigned,const NetworkId&,const NetworkId&,const NetworkId&,const NetworkEndpoint&,std::uint64_t,std::uint64_t,const Buffer&);
  bool exchange(const Buffer&,Buffer&,unsigned,int);
  int fd_=-1;std::string own_,controller_;unsigned controller_uid_;std::uint64_t generation_;
};
class NetworkServer {
public:
  using Events=std::function<void(const std::string&)>;
  using Clock=std::function<std::uint64_t()>;
  NetworkServer(const NetworkCrypto&,NetworkConfig,Buffer,ControllerAuthority&,Events={},Clock={});
  ~NetworkServer();
  void set_boot(const NetworkId&,std::uint64_t);
  Buffer process(const unsigned char*,std::size_t,const NetworkEndpoint&,std::uint64_t);
  Buffer telemetry(std::uint64_t);
  void expire(std::uint64_t);
  void stop(std::uint64_t);
  std::string status_json(std::uint64_t now)const;
  bool session_active()const{return active_;}
  NetworkEndpoint endpoint()const{return endpoint_;}
  std::uint64_t count(const std::string& key)const{return counters_.at(key);}
private:
  Clock clock_;
  bool refresh(std::uint64_t);
  void end_session(std::uint64_t);
  Buffer hello(const NetworkPacket&,const NetworkEndpoint&,std::uint64_t);
  Buffer ack(const NetworkId&,unsigned,unsigned,unsigned,std::uint64_t,bool);
  Buffer send(wire::MessageType,const Buffer&,std::uint64_t);
  const NetworkCrypto& crypto_;NetworkConfig config_;Buffer key_;ControllerAuthority& authority_;Events events_;
  NetworkId boot_{},session_{},nonce_{};NetworkEndpoint endpoint_{};
  bool active_=false,fresh_=false;TelemetrySnapshot snapshot_{};Buffer cached_ack_;
  std::uint64_t hello_us_=0,last_rx_us_=0,rx_sequence_=0,tx_sequence_=0,last_command_us_=0,last_command_sequence_=0,token_us_=0;
  double tokens_=0;std::map<std::string,std::uint64_t> counters_;
};
void notify_systemd(const std::string&);
} // namespace phantom
