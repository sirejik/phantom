cmake_minimum_required(VERSION 3.7)
project(phantom_ev3_bench LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(ev3-bench
    src/main.cpp
    src/sysfs.cpp
)
target_include_directories(ev3-bench PRIVATE include)
target_compile_options(ev3-bench PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(ev3-bench PRIVATE pthread)

install(TARGETS ev3-bench RUNTIME DESTINATION bin)
