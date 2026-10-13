#include "phantom/network_server.hpp"
#include "phantom/json_reader.hpp"
#include "phantom/robot_data.hpp"
#include "phantom/byte_codec.hpp"
#include <algorithm>
#include <cstring>
#include <sstream>
#include <stdexcept>
namespace phantom {
namespace {
JsonValue read_json(const std::string& path){JsonValue value;std::string error;if(!parse_json(read_bounded_file(path),value,error))throw std::runtime_error("invalid runtime JSON");return value;}
std::string string_field(const JsonValue& root,const std::string& key){std::string result;if(!json_string(root,key,result))throw std::runtime_error("required network field missing: "+key);return result;}
unsigned integer_field(const JsonValue& root,const std::string& key,unsigned min,unsigned max){std::uint64_t result=0;if(!json_uint(root,key,min,max,result))throw std::runtime_error("invalid network bound: "+key);return result;}
bool qualified_network_only(const JsonValue& root){bool value=false;std::uint64_t scope=1,observation=1;
  return json_bool(root,"qualification_only",value)&&value&&json_uint(root,"actuator_scope_mask",0,0,scope)&&json_uint(root,"safety_observation_mask",0,0,observation);}
void id32(Buffer& payload,std::size_t offset,const std::string& value){
  if(value.empty()||value.size()>=32||!std::all_of(value.begin(),value.end(),[](unsigned char c){return (c>='A'&&c<='Z')||(c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='.'||c=='_'||c=='-';}))throw std::runtime_error("invalid robot/profile id");
  std::copy(value.begin(),value.end(),payload.begin()+offset);
}
}
NetworkConfig load_network_config(const NetworkCrypto& crypto,const std::string& config_path,const std::string& bundle_path,const std::string& manifest_path){
  const auto config=read_json(config_path),manifest=read_json(manifest_path);
  JsonValue bundle; std::string canonical,error;
  if(!load_robot_data(bundle_path,true,bundle,canonical,error))throw std::runtime_error(error);
  // The current network process accepts only the canonical zero-authority
  // descriptor. A saved physical bundle is never downgraded or overwritten.
  if(canonical!=network_only_descriptor_json())throw std::runtime_error("network-only session descriptor mismatch");
  if(string_field(config,"build_profile")!="Diagnostic"||!qualified_network_only(config)||!qualified_network_only(bundle))throw std::runtime_error("Stage-3 network-only profile required");
  if(string_field(config,"network/discovery_service_type")!="_phantom-ev3._udp"||string_field(config,"network/discovery_domain")!="local."||string_field(config,"network/ip_family")!="IPV4")throw std::runtime_error("DNS-SD/IP family mismatch");
  NetworkConfig result;result.robot_id=string_field(config,"robot_id");Buffer test_id(32);id32(test_id,0,result.robot_id);
  result.build_id=string_field(manifest,"build_id");Digest check{};if(!parse_hex(result.build_id,check.data(),check.size()))throw std::runtime_error("invalid build_id");
  if(!parse_hex(string_field(manifest,"protocol_contract_hash"),result.contract_hash.data(),result.contract_hash.size())||string_field(manifest,"protocol_contract_hash")!=wire::kProtocolContractSha256)throw std::runtime_error("protocol contract mismatch");
  result.bundle_hash=crypto.hash(reinterpret_cast<const unsigned char*>(canonical.data()),canonical.size());
  if(hex(result.bundle_hash.data(),result.bundle_hash.size())!=string_field(manifest,"commissioning_bundle_hash"))throw std::runtime_error("bundle/manifest hash mismatch");
  result.port=integer_field(config,"network/listen_port_udp",1,65535);result.rate=integer_field(config,"network/rx_rate_limit_pps",1,10000);
  result.burst=integer_field(config,"network/rx_burst_packets",1,1024);result.retry_ms=integer_field(config,"network/hello_retry_window_ms",100,60000);
  result.stale_ms=integer_field(config,"network/session_stale_ms",200,300000);return result;
}
NetworkServer::NetworkServer(const NetworkCrypto& crypto,NetworkConfig config,Buffer key,ControllerAuthority& authority,Events events,Clock clock)
  :clock_(std::move(clock)),crypto_(crypto),config_(std::move(config)),key_(std::move(key)),authority_(authority),events_(std::move(events)),tokens_(config_.burst){
  if(key_.size()<32||!config_.burst||!config_.rate)throw std::runtime_error("invalid network inputs");
  for(const auto name:{"rx","rx_drop","hmac_fail","parser_reject","hello_accept","hello_reject","replay_reject","pong","telemetry","command_scope_zero","motor_write_attempts_rejected","controller_snapshot_stale"})counters_[name]=0;
}
NetworkServer::~NetworkServer(){std::fill(key_.begin(),key_.end(),0);}
void NetworkServer::set_boot(const NetworkId& boot,std::uint64_t now){
  if(bytes::zero(boot.data(),boot.size()))throw std::runtime_error("invalid controller boot id");
  if(boot!=boot_){end_session(now);fresh_=false;boot_=boot;}
}
void NetworkServer::end_session(std::uint64_t now){
  if(active_)authority_.invalidate(boot_,session_,endpoint_,now);
  active_=false;session_.fill(0);nonce_.fill(0);cached_ack_.clear();rx_sequence_=tx_sequence_=last_command_sequence_=last_command_us_=0;
}
void NetworkServer::stop(std::uint64_t now){end_session(now);fresh_=false;}
void NetworkServer::expire(std::uint64_t now){if(active_&&(now<last_rx_us_||now-last_rx_us_>std::uint64_t(config_.stale_ms)*1000))end_session(now);}
bool NetworkServer::refresh(std::uint64_t now){
  TelemetrySnapshot candidate;
  const bool received=authority_.snapshot(boot_,now,candidate);
  // A synchronous IPC reply may contain a sample acquired after request time.
  // Compare with receipt time; future samples and the 100-ms limit remain rejected.
  const auto observed=clock_?clock_():now;
  if(!received||observed<now||candidate.monotonic_us>observed||observed-candidate.monotonic_us>100000){
    fresh_=false;++counters_["controller_snapshot_stale"];return false;
  }
  snapshot_=candidate;fresh_=true;return true;
}
Buffer NetworkServer::ack(const NetworkId& nonce,unsigned result,unsigned slot,unsigned role,std::uint64_t now,bool accepted){
  Buffer payload(wire::kHelloAckPayloadBytes,0);std::copy(nonce.begin(),nonce.end(),payload.begin());id32(payload,wire::kHelloAckOffsetRobotId,config_.robot_id);
  parse_hex(config_.build_id,payload.data()+wire::kHelloAckOffsetBuildId,32);payload[wire::kHelloAckOffsetAcceptedKeySlot]=slot;payload[wire::kHelloAckOffsetAcceptedRole]=role;
  std::copy(config_.contract_hash.begin(),config_.contract_hash.end(),payload.begin()+wire::kHelloAckOffsetProtocolContractHash);
  std::copy(config_.bundle_hash.begin(),config_.bundle_hash.end(),payload.begin()+wire::kHelloAckOffsetCommissioningBundleHash);
  bytes::put16(payload.data()+wire::kHelloAckOffsetState,snapshot_.state);payload[wire::kHelloAckOffsetBuildProfile]=static_cast<unsigned>(wire::BuildProfile::DIAGNOSTIC);
  bytes::put16(payload.data()+wire::kHelloAckOffsetResultCode,result);NetworkPacket packet;packet.type=wire::MessageType::HELLO_ACK;packet.boot=boot_;if(accepted)packet.session=session_;packet.sender_us=now;packet.payload=std::move(payload);
  return encode_wire(crypto_,key_,packet);
}
Buffer NetworkServer::hello(const NetworkPacket& packet,const NetworkEndpoint& address,std::uint64_t now){
  const auto*p=packet.payload.data();NetworkId nonce{};std::copy(p+wire::kHelloOffsetClientNonce,p+wire::kHelloOffsetCapabilitiesRequested,nonce.begin());
  if(!bytes::zero(packet.session.data(),16)||packet.sequence||packet.boot!=boot_){++counters_["hello_reject"];return {};}
  if(!refresh(now)){++counters_["hello_reject"];return {};}
  auto reject=[&](wire::ResultCode result){++counters_["hello_reject"];return ack(nonce,static_cast<unsigned>(result),p[wire::kHelloOffsetKeySlot],p[wire::kHelloOffsetSessionRole],now,false);};
  if(p[wire::kHelloOffsetKeySlot]||p[wire::kHelloOffsetSessionRole])return reject(wire::ResultCode::ERR_AUTH);
  const std::string robot(reinterpret_cast<const char*>(p));
  if(robot!=config_.robot_id)return reject(wire::ResultCode::ERR_SESSION);
  if(bytes::u16(p+wire::kHelloOffsetProtocolMinor)||bytes::u32(p+wire::kHelloOffsetCapabilitiesRequested))return reject(wire::ResultCode::ERR_UNSUPPORTED);
  if(active_&&address==endpoint_&&nonce==nonce_&&now>=hello_us_&&now-hello_us_<=std::uint64_t(config_.retry_ms)*1000)return cached_ack_;
  expire(now);if(active_)return reject(wire::ResultCode::ERR_CONTROL_SESSION_BUSY);
  const auto candidate=crypto_.random_id();const auto result=authority_.open(boot_,candidate,nonce,address,now);
  if(result!=static_cast<unsigned>(wire::ResultCode::OK)){++counters_["hello_reject"];return ack(nonce,result,p[wire::kHelloOffsetKeySlot],p[wire::kHelloOffsetSessionRole],now,false);}
  session_=candidate;endpoint_=address;nonce_=nonce;active_=true;hello_us_=last_rx_us_=now;rx_sequence_=tx_sequence_=last_command_us_=last_command_sequence_=0;
  if(!refresh(now)){end_session(now);return {};}
  cached_ack_=ack(nonce,0,0,0,now,true);++counters_["hello_accept"];if(events_)events_("HELLO_ACCEPTED");return cached_ack_;
}
Buffer NetworkServer::send(wire::MessageType type,const Buffer& payload,std::uint64_t now){
  if(tx_sequence_==UINT64_MAX){end_session(now);return {};}
  NetworkPacket packet;packet.type=type;packet.session=session_;packet.boot=boot_;packet.sequence=++tx_sequence_;packet.sender_us=now;packet.payload=payload;return encode_wire(crypto_,key_,packet);
}
Buffer NetworkServer::process(const unsigned char* data,std::size_t size,const NetworkEndpoint& address,std::uint64_t now){
  ++counters_["rx"];if(!wire_header_valid(data,size)){++counters_["parser_reject"];return {};}
  if(token_us_&&now>=token_us_)tokens_=std::min(double(config_.burst),tokens_+double(now-token_us_)*config_.rate/1000000);
  token_us_=now;
  if(tokens_<1){++counters_["rx_drop"];return {};}tokens_-=1;
  if(bytes::u16(data+6)==static_cast<unsigned>(wire::MessageType::HELLO)&&data[wire::kHeaderBytes+wire::kHelloOffsetKeySlot]!=0){++counters_["hello_reject"];return {};}
  NetworkPacket packet;const auto decoded=decode_wire(crypto_,key_,data,size,packet);
  if(decoded!=DecodeResult::Ok){++counters_[decoded==DecodeResult::Authentication?"hmac_fail":"parser_reject"];return {};}
  if(packet.type==wire::MessageType::HELLO)return hello(packet,address,now);
  expire(now);
  if(!active_||!(address==endpoint_)||packet.session!=session_||packet.boot!=boot_){++counters_["parser_reject"];return {};}
  if(packet.sequence<=rx_sequence_){++counters_["replay_reject"];return {};}
  if(packet.type!=wire::MessageType::PING&&packet.type!=wire::MessageType::COMMAND){++counters_["parser_reject"];return {};}
  rx_sequence_=packet.sequence;last_rx_us_=now;
  if(packet.type==wire::MessageType::PING){++counters_["pong"];return send(wire::MessageType::PONG,packet.payload,now);}
  if(authority_.command(boot_,session_,endpoint_,packet.sequence,now,packet.payload)!=0){end_session(now);return {};}
  last_command_us_=now;last_command_sequence_=packet.sequence;++counters_["command_scope_zero"];
  if(bytes::u32(packet.payload.data())&wire::kCommandMotionFlagsMotionEnable)++counters_["motor_write_attempts_rejected"];
  return {};
}
Buffer NetworkServer::telemetry(std::uint64_t now){
  expire(now);if(!active_||!refresh(now))return {};
  Buffer p(wire::kTelemetryPayloadBytes,0);id32(p,0,config_.robot_id);parse_hex(config_.build_id,p.data()+wire::kTelemetryOffsetBuildId,32);
  std::copy(config_.bundle_hash.begin(),config_.bundle_hash.end(),p.begin()+wire::kTelemetryOffsetCommissioningBundleHash);
  bytes::put16(p.data()+wire::kTelemetryOffsetState,snapshot_.state);bytes::put16(p.data()+wire::kTelemetryOffsetFaultCode,snapshot_.fault_code);bytes::put32(p.data()+wire::kTelemetryOffsetStatusFlags,snapshot_.status_flags);
  std::copy(snapshot_.incident_id.begin(),snapshot_.incident_id.end(),p.begin()+wire::kTelemetryOffsetIncidentId);bytes::put64(p.data()+wire::kTelemetryOffsetLastAcceptedCommandSequence,last_command_sequence_);
  const auto age=last_command_us_&&now>=last_command_us_?std::min<std::uint64_t>(UINT32_MAX,(now-last_command_us_)/1000):UINT32_MAX;
  bytes::put32(p.data()+wire::kTelemetryOffsetCommandAgeMs,static_cast<unsigned>(age));
  for(std::size_t i=0;i<3;++i){bytes::putf(p.data()+wire::kTelemetryOffsetQActualRad+i*4,snapshot_.q_actual[i]);bytes::putf(p.data()+wire::kTelemetryOffsetQSpeedRadS+i*4,snapshot_.q_speed[i]);}
  bytes::putf(p.data()+wire::kTelemetryOffsetGripActual,snapshot_.grip_actual);bytes::put16(p.data()+wire::kTelemetryOffsetGripState,snapshot_.grip_state);bytes::put16(p.data()+wire::kTelemetryOffsetBatteryMv,snapshot_.battery_mv);
  auto flags=snapshot_.loop_health_flags;if(counters_["rx_drop"])flags|=wire::kLoopHealthFlagsNetworkBackpressureSeen;
  bytes::put32(p.data()+wire::kTelemetryOffsetLoopHealthFlags,flags);id32(p,wire::kTelemetryOffsetActivePayloadProfileId,"UNSELECTED");p[wire::kTelemetryOffsetPayloadState]=static_cast<unsigned>(wire::PayloadState::UNKNOWN);p[wire::kTelemetryOffsetBuildProfile]=1;
  ++counters_["telemetry"];return send(wire::MessageType::TELEMETRY,p,now);
}
std::string NetworkServer::status_json(std::uint64_t now)const{
  const bool observable=fresh_&&snapshot_.monotonic_us<=now&&now-snapshot_.monotonic_us<=100000;
  std::ostringstream s;s<<"{\"schema_version\":2,\"profile\":\"stage3-network-only\",\"robot_id\":\""<<config_.robot_id<<"\",\"port\":"<<config_.port<<",\"controller_boot_id\":\""<<hex(boot_.data(),boot_.size())<<"\",\"session_active\":"<<(active_?"true":"false")<<",\"actuator_scope_mask\":0,\"qualification_only\":true,\"controller_snapshot_fresh\":"<<(observable?"true":"false")<<",\"controller_state\":";
  if(observable)s<<snapshot_.state;else s<<"null";s<<",\"controller_fault_code\":";if(observable)s<<snapshot_.fault_code;else s<<"null";s<<",\"counters\":{";
  bool first=true;for(const auto& item:counters_){if(!first)s<<',';first=false;s<<'"'<<item.first<<"\":"<<item.second;}s<<"}}\n";return s.str();
}
} // namespace phantom
