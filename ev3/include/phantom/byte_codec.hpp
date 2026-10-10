#pragma once
#include <cstdint>
#include <cstring>
namespace phantom { namespace bytes {
inline std::uint16_t u16(const unsigned char*p){return std::uint16_t(p[0])|std::uint16_t(p[1])<<8;}
inline std::uint32_t u32(const unsigned char*p){return std::uint32_t(p[0])|std::uint32_t(p[1])<<8|std::uint32_t(p[2])<<16|std::uint32_t(p[3])<<24;}
inline std::uint64_t u64(const unsigned char*p){std::uint64_t v=0;for(int i=7;i>=0;--i)v=(v<<8)|p[i];return v;}
inline void put16(unsigned char*p,std::uint16_t v){p[0]=v&255;p[1]=(v>>8)&255;}
inline void put32(unsigned char*p,std::uint32_t v){for(int i=0;i<4;++i)p[i]=(v>>(8*i))&255;}
inline void put64(unsigned char*p,std::uint64_t v){for(int i=0;i<8;++i)p[i]=(v>>(8*i))&255;}
inline void putf(unsigned char*p,float v){std::uint32_t bits=0;std::memcpy(&bits,&v,4);put32(p,bits);}
inline float f32(const unsigned char*p){const auto bits=u32(p);float v=0;std::memcpy(&v,&bits,4);return v;}
inline bool zero(const unsigned char*p,std::size_t n){for(std::size_t i=0;i<n;++i)if(p[i])return false;return true;}
} }
