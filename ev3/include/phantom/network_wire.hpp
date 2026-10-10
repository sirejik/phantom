#pragma once
#include "protocol_constants.hpp"
#include <array>
#include <string>
#include <vector>
namespace phantom {
using NetworkId=std::array<unsigned char,16>;
using Digest=std::array<unsigned char,32>;
using Buffer=std::vector<unsigned char>;
// OpenSSL's stable one-shot ABI avoids a second crypto implementation and
// a build-time dependency on headers absent from the pinned cross image.
class NetworkCrypto {
public:
  NetworkCrypto();~NetworkCrypto();
  NetworkCrypto(const NetworkCrypto&)=delete;NetworkCrypto& operator=(const NetworkCrypto&)=delete;
  Digest hash(const unsigned char*,std::size_t) const;
  Digest hmac(const Buffer&,const unsigned char*,std::size_t) const;
  NetworkId random_id() const;
  bool equal(const unsigned char*,const unsigned char*,std::size_t) const;
private:
  void* library_=nullptr;
  const void* (*sha256_method_)()=nullptr;
  unsigned char* (*hmac_)(const void*,const void*,int,const unsigned char*,std::size_t,unsigned char*,unsigned*)=nullptr;
  unsigned char* (*hash_)(const unsigned char*,std::size_t,unsigned char*)=nullptr;
  int (*random_)(unsigned char*,int)=nullptr;
  int (*compare_)(const void*,const void*,std::size_t)=nullptr;
};
struct NetworkPacket {
  wire::MessageType type{};NetworkId session{},boot{};
  std::uint64_t sequence=0,sender_us=0;Buffer payload;
};
enum class DecodeResult { Ok, Format, Authentication };
bool wire_header_valid(const unsigned char*,std::size_t);
DecodeResult decode_wire(const NetworkCrypto&,const Buffer&,const unsigned char*,std::size_t,NetworkPacket&);
Buffer encode_wire(const NetworkCrypto&,const Buffer&,const NetworkPacket&);
bool parse_hex(const std::string&,unsigned char*,std::size_t);
std::string hex(const unsigned char*,std::size_t);
std::string read_bounded_file(const std::string&,std::size_t=262144);
Buffer read_control_key(const std::string&);
} // namespace phantom
