#pragma once
#include "phantom/motor_backend.hpp"
#include <array>
#include <atomic>
#include <cstdint>

namespace phantom {
enum class State:std::uint16_t { Boot=0,UserCalibration=1,Discovery=2,ConnectedUnreferenced=3,RobotCalibration=4,Ready=5,Hold=6,Tracking=7,SafeHold=8,Stopped=9,Commissioning=10 };
enum class Fault:std::uint16_t { None=0,Timeout=100,Config=101,Limit=102,JointStall=103,Gripper=104,Reference=105,Localization=106,ControllerProcess=107,LoopOverrun=108,Security=109,MotorOverload=110,Space=111,GripperHome=112,CollisionSet=113,PayloadProfile=114,HoldOverload=115,BatteryLow=116 };
struct Target { std::uint64_t sequence=0,received_us=0; std::uint32_t motion_flags=0; std::array<float,3> q{}; float grip=0; };
struct RuntimeConfig { std::uint32_t command_timeout_ms=120; bool commissioning_valid=false,measured_limits_complete=false,external_power_cut_tested=false; std::array<float,3> q_min{{0,0,0}},q_max{{0,0,0}},max_velocity{{0,0,0}}; };
struct FlightSample { std::uint64_t monotonic_us=0,command_sequence=0; std::uint32_t loop_dt_us=0,status_flags=0; State state=State::Boot; Fault fault=Fault::None; std::array<std::int32_t,4> encoder{}; std::array<std::int16_t,4> duty{}; };
template<std::size_t N> class FixedRing { public:void push(const FlightSample& s) noexcept { data_[head_]=s;head_=(head_+1)%N;if(size_<N)++size_;}std::size_t size()const{return size_;}const FlightSample& newest()const{return data_[(head_+N-1)%N];}private:std::array<FlightSample,N> data_{};std::size_t head_=0,size_=0;};

class ControllerCore {
public:
  ControllerCore(MotorBackend& backend,const RuntimeConfig& config):backend_(backend),config_(config){}
  bool initialize(); void set_safety_heartbeat_alive(bool alive){safety_alive_=alive;} void set_references_valid(bool joints,bool gripper){joint_reference_=joints;gripper_reference_=gripper;}
  bool publish_target(const Target& target); void tick(std::uint64_t now_us,std::uint32_t dt_us) noexcept; void shutdown() noexcept;
  State state()const{return state_;}Fault fault()const{return fault_;}bool motion_allowed()const{return motion_allowed_;}const FixedRing<500>& recorder()const{return recorder_;}
private:
  void safe(State state,Fault fault=Fault::None) noexcept; bool ready_predicates()const noexcept;
  MotorBackend& backend_;RuntimeConfig config_;Target target_{};std::uint64_t last_sequence_=0;State state_=State::Boot;Fault fault_=Fault::None;bool safety_alive_=false,joint_reference_=false,gripper_reference_=false,motion_allowed_=false;FixedRing<500> recorder_;
};
}
