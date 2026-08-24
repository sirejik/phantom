set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR arm)

set(EV3_TOOLCHAIN_PREFIX "arm-linux-gnueabi" CACHE STRING "GNU armel toolchain prefix")
set(CMAKE_C_COMPILER "${EV3_TOOLCHAIN_PREFIX}-gcc")
set(CMAKE_CXX_COMPILER "${EV3_TOOLCHAIN_PREFIX}-g++")

# EV3's ARM926EJ-S implements ARMv5TEJ and has no hardware floating point.
set(CMAKE_C_FLAGS_INIT "-march=armv5te -mfloat-abi=soft")
set(CMAKE_CXX_FLAGS_INIT "-march=armv5te -mfloat-abi=soft")
