#include "phantom/network_wire.hpp"
#include "phantom/byte_codec.hpp"
#include <climits>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <dlfcn.h>
#include <fstream>
#include <stdexcept>
#include <sys/stat.h>
namespace phantom {
namespace {
template<class T> T symbol(void* handle,const char* name){
  auto result=reinterpret_cast<T>(::dlsym(handle,name));
  if(!result)throw std::runtime_error(std::string("OpenSSL symbol unavailable: ")+name);
  return result;
}
bool id32_valid(const unsigned char*p){
  std::size_t end=0;while(end<32&&p[end]){if(p[end]>127) return false;++end;}
  return end>0&&end<32&&bytes::zero(p+end,32-end);
}
bool payload_valid(wire::MessageType type,const Buffer& payload){
  if(!wire::PayloadFieldsValid(type,payload.data(),payload.size()))return false;
  const auto*p=payload.data();
  if(type==wire::MessageType::HELLO)return id32_valid(p)&&p[wire::kHelloOffsetKeySlot]<=1&&p[wire::kHelloOffsetSessionRole]<=1;
  if(type==wire::MessageType::COMMAND){
    if(bytes::u32(p)&~wire::kCommandMotionFlagsMask)return false;
    for(int i=0;i<3;++i)if(std::fabs(bytes::f32(p+wire::kCommandOffsetQBaseRad+i*4))>6.4f)return false;
    return bytes::f32(p+wire::kCommandOffsetGripIntent)>=0&&bytes::f32(p+wire::kCommandOffsetGripIntent)<=1;
  }
  if(type==wire::MessageType::HELLO_ACK){
    const auto result=bytes::u16(p+wire::kHelloAckOffsetResultCode);
    return id32_valid(p+wire::kHelloAckOffsetRobotId)&&bytes::u16(p+wire::kHelloAckOffsetProtocolMinor)==0&&p[wire::kHelloAckOffsetAcceptedKeySlot]<=1&&p[wire::kHelloAckOffsetAcceptedRole]<=1&&
      (result!=0||p[wire::kHelloAckOffsetAcceptedKeySlot]==p[wire::kHelloAckOffsetAcceptedRole])&&bytes::u16(p+wire::kHelloAckOffsetState)<=10&&!(bytes::u16(p+wire::kHelloAckOffsetReferenceFlags)&~3)&&p[wire::kHelloAckOffsetBuildProfile]<=1&&!(p[wire::kHelloAckOffsetGripperCapabilities]&~3)&&result<=15;
  }
  if(type==wire::MessageType::TELEMETRY){
    const auto fault=bytes::u16(p+wire::kTelemetryOffsetFaultCode);
    return id32_valid(p)&&id32_valid(p+wire::kTelemetryOffsetActivePayloadProfileId)&&bytes::u16(p+wire::kTelemetryOffsetState)<=10&&(!fault||(fault>=100&&fault<=116))&&
      !(bytes::u32(p+wire::kTelemetryOffsetStatusFlags)&~wire::kTelemetryStatusFlagsMask)&&bytes::u16(p+wire::kTelemetryOffsetGripState)<=5&&
      !(bytes::u32(p+wire::kTelemetryOffsetLoopHealthFlags)&~wire::kLoopHealthFlagsMask)&&p[wire::kTelemetryOffsetPayloadState]<=2&&p[wire::kTelemetryOffsetBuildProfile]<=1;
  }
  return true;
}
}
NetworkCrypto::NetworkCrypto(){
  for(const auto name:{"libcrypto.so.1.0.2","libcrypto.so.1.1","libcrypto.so.3"}){library_=::dlopen(name,RTLD_NOW|RTLD_LOCAL);if(library_)break;}
  if(!library_)throw std::runtime_error("OpenSSL libcrypto unavailable");
  try{
    sha256_method_=symbol<decltype(sha256_method_)>(library_,"EVP_sha256");
    hmac_=symbol<decltype(hmac_)>(library_,"HMAC");hash_=symbol<decltype(hash_)>(library_,"SHA256");
    random_=symbol<decltype(random_)>(library_,"RAND_bytes");compare_=symbol<decltype(compare_)>(library_,"CRYPTO_memcmp");
  }catch(...){::dlclose(library_);library_=nullptr;throw;}
}
NetworkCrypto::~NetworkCrypto(){if(library_)::dlclose(library_);}
Digest NetworkCrypto::hash(const unsigned char*p,std::size_t n) const{
  Digest result{};if(!hash_(p,n,result.data()))throw std::runtime_error("SHA256 failed");return result;
}
Digest NetworkCrypto::hmac(const Buffer& key,const unsigned char*p,std::size_t n) const{
  if(key.size()<32||key.size()>INT_MAX)throw std::runtime_error("invalid CONTROL key length");
  Digest result{};unsigned size=0;
  if(!hmac_(sha256_method_(),key.data(),static_cast<int>(key.size()),p,n,result.data(),&size)||size!=result.size())throw std::runtime_error("HMAC failed");
  return result;
}
NetworkId NetworkCrypto::random_id() const{
  NetworkId id{};do{if(random_(id.data(),id.size())!=1)throw std::runtime_error("secure random unavailable");}while(bytes::zero(id.data(),id.size()));return id;
}
bool NetworkCrypto::equal(const unsigned char*a,const unsigned char*b,std::size_t n) const{return compare_(a,b,n)==0;}
bool wire_header_valid(const unsigned char*p,std::size_t size){
  if(size<wire::kHeaderBytes+wire::kHmacBytes||size>wire::kMaxDatagramBytes)return false;
  const auto payload=wire::PayloadBytes(static_cast<wire::MessageType>(bytes::u16(p+6)));
  return std::memcmp(p,"PHNT",4)==0&&bytes::u16(p+4)==1&&bytes::u16(p+8)==wire::kHeaderBytes&&
    bytes::u16(p+10)==payload&&payload>0&&!bytes::u32(p+12)&&size==wire::kHeaderBytes+payload+wire::kHmacBytes;
}
DecodeResult decode_wire(const NetworkCrypto& crypto,const Buffer& key,const unsigned char*p,std::size_t size,NetworkPacket& out){
  if(!wire_header_valid(p,size))return DecodeResult::Format;
  const auto digest=crypto.hmac(key,p,size-wire::kHmacBytes);
  if(!crypto.equal(digest.data(),p+size-wire::kHmacBytes,digest.size()))return DecodeResult::Authentication;
  NetworkPacket candidate;candidate.type=static_cast<wire::MessageType>(bytes::u16(p+6));
  std::copy(p+16,p+32,candidate.session.begin());std::copy(p+32,p+48,candidate.boot.begin());
  candidate.sequence=bytes::u64(p+48);candidate.sender_us=bytes::u64(p+56);
  candidate.payload.assign(p+wire::kHeaderBytes,p+size-wire::kHmacBytes);
  if(!payload_valid(candidate.type,candidate.payload))return DecodeResult::Format;
  out=std::move(candidate);return DecodeResult::Ok;
}
Buffer encode_wire(const NetworkCrypto& crypto,const Buffer& key,const NetworkPacket& packet){
  if(packet.payload.size()!=wire::PayloadBytes(packet.type)||!payload_valid(packet.type,packet.payload))throw std::runtime_error("invalid wire payload");
  Buffer out(wire::kHeaderBytes+packet.payload.size()+wire::kHmacBytes,0);
  std::memcpy(out.data(),"PHNT",4);bytes::put16(out.data()+4,1);bytes::put16(out.data()+6,static_cast<unsigned>(packet.type));
  bytes::put16(out.data()+8,wire::kHeaderBytes);bytes::put16(out.data()+10,packet.payload.size());
  std::copy(packet.session.begin(),packet.session.end(),out.begin()+16);std::copy(packet.boot.begin(),packet.boot.end(),out.begin()+32);
  bytes::put64(out.data()+48,packet.sequence);bytes::put64(out.data()+56,packet.sender_us);
  std::copy(packet.payload.begin(),packet.payload.end(),out.begin()+wire::kHeaderBytes);
  const auto digest=crypto.hmac(key,out.data(),out.size()-wire::kHmacBytes);std::copy(digest.begin(),digest.end(),out.end()-wire::kHmacBytes);
  return out;
}
bool parse_hex(const std::string& value,unsigned char*out,std::size_t n){
  if(value.size()!=n*2)return false;
  auto digit=[](char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:-1;};
  for(std::size_t i=0;i<n;++i){const int hi=digit(value[2*i]),lo=digit(value[2*i+1]);if(hi<0||lo<0)return false;out[i]=(hi<<4)|lo;}return true;
}
std::string hex(const unsigned char*p,std::size_t n){std::string out;out.reserve(n*2);for(std::size_t i=0;i<n;++i){out+="0123456789abcdef"[p[i]>>4];out+="0123456789abcdef"[p[i]&15];}return out;}
std::string read_bounded_file(const std::string& path,std::size_t limit){
  std::ifstream stream(path,std::ios::binary);if(!stream)throw std::runtime_error("required input unavailable");
  std::string result;char chunk[4096];while(stream){stream.read(chunk,sizeof(chunk));result.append(chunk,static_cast<std::size_t>(stream.gcount()));if(result.size()>limit)throw std::runtime_error("input exceeds bound");}return result;
}
Buffer read_control_key(const std::string& path){
  struct stat st{};if(::stat(path.c_str(),&st)||!S_ISREG(st.st_mode)||(st.st_mode&0027))throw std::runtime_error("CONTROL key permissions invalid");
  auto raw=read_bounded_file(path,4096);Buffer result(raw.begin(),raw.end());
  if(raw.size()==64){Digest key{};std::string lower=raw;for(auto& c:lower)if(c>='A'&&c<='F')c+=32;if(parse_hex(lower,key.data(),key.size()))result.assign(key.begin(),key.end());}
  std::fill(raw.begin(),raw.end(),0);if(result.size()<32)throw std::runtime_error("CONTROL key too short");return result;
}
} // namespace phantom
