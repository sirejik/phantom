#pragma once
#include "phantom/motor_backend.hpp"
#include "protocol_constants.hpp"
#include <array>
#include <atomic>
#include <cstdint>
#include <string>

namespace phantom {
enum class State:std::uint16_t { Boot=(std::uint16_t)wire::State::BOOT,UserCalibration=(std::uint16_t)wire::State::USER_CALIBRATION,Discovery=(std::uint16_t)wire::State::DISCOVERY,ConnectedUnreferenced=(std::uint16_t)wire::State::CONNECTED_UNREFERENCED,RobotCalibration=(std::uint16_t)wire::State::ROBOT_CALIBRATION,Ready=(std::uint16_t)wire::State::READY,Hold=(std::uint16_t)wire::State::HOLD,Tracking=(std::uint16_t)wire::State::TRACKING,SafeHold=(std::uint16_t)wire::State::SAFE_HOLD,Stopped=(std::uint16_t)wire::State::STOPPED,Commissioning=(std::uint16_t)wire::State::COMMISSIONING };
enum class Fault:std::uint16_t { None=(std::uint16_t)wire::Fault::NONE,Timeout=(std::uint16_t)wire::Fault::FAULT_TIMEOUT,Config=(std::uint16_t)wire::Fault::FAULT_CONFIG,Limit=(std::uint16_t)wire::Fault::FAULT_LIMIT,JointStall=(std::uint16_t)wire::Fault::FAULT_JOINT_STALL,Gripper=(std::uint16_t)wire::Fault::FAULT_GRIPPER,Reference=(std::uint16_t)wire::Fault::FAULT_REFERENCE,Localization=(std::uint16_t)wire::Fault::FAULT_LOCALIZATION,ControllerProcess=(std::uint16_t)wire::Fault::FAULT_CONTROLLER_PROCESS,LoopOverrun=(std::uint16_t)wire::Fault::FAULT_LOOP_OVERRUN,Security=(std::uint16_t)wire::Fault::FAULT_SECURITY,MotorOverload=(std::uint16_t)wire::Fault::FAULT_MOTOR_OVERLOAD,Space=(std::uint16_t)wire::Fault::FAULT_SPACE,GripperHome=(std::uint16_t)wire::Fault::FAULT_GRIPPER_HOME,CollisionSet=(std::uint16_t)wire::Fault::FAULT_COLLISION_SET,PayloadProfile=(std::uint16_t)wire::Fault::FAULT_PAYLOAD_PROFILE,HoldOverload=(std::uint16_t)wire::Fault::FAULT_HOLD_OVERLOAD,BatteryLow=(std::uint16_t)wire::Fault::FAULT_BATTERY_LOW };
struct Target { std::uint64_t sequence=0,received_us=0; std::uint32_t motion_flags=0; std::array<float,3> q{}; float grip=0; };
struct RuntimeConfig { std::uint32_t command_timeout_ms=120; bool commissioning_valid=false,measured_limits_complete=false,external_power_cut_tested=false,qualification_only=false;std::uint8_t actuator_scope_mask=0x0f; std::array<float,3> q_min{{0,0,0}},q_max{{0,0,0}},max_velocity{{0,0,0}}; };
struct FlightSample { std::uint64_t monotonic_us=0,command_sequence=0; std::uint32_t loop_dt_us=0,status_flags=0; State state=State::Boot; Fault fault=Fault::None; std::array<std::int32_t,4> encoder{}; std::array<std::int16_t,4> duty{}; };
template<std::size_t N> class FixedRing { public:void push(const FlightSample& s) noexcept { data_[head_]=s;head_=(head_+1)%N;if(size_<N)++size_;}std::size_t size()const{return size_;}const FlightSample& newest()const{return data_[(head_+N-1)%N];}private:std::array<FlightSample,N> data_{};std::size_t head_=0,size_=0;};

class ControllerCore {
public:
  ControllerCore(MotorBackend& backend,const RuntimeConfig& config):backend_(backend),config_(config){}
  bool initialize(); void set_safety_heartbeat_alive(bool alive){safety_alive_=alive;} void set_references_valid(bool joints,bool gripper){joint_reference_=joints;gripper_reference_=gripper;}
  void set_network_session_active(bool active){network_session_active_=active;}
  bool publish_target(const Target& target); void tick(std::uint64_t now_us,std::uint32_t dt_us) noexcept; void shutdown() noexcept;
  State state()const{return state_;}Fault fault()const{return fault_;}bool motion_allowed()const{return motion_allowed_;}const std::string& initialization_error()const{return initialization_error_;}const FixedRing<500>& recorder()const{return recorder_;}
private:
  void safe(State state,Fault fault=Fault::None) noexcept; bool ready_predicates()const noexcept;
  MotorBackend& backend_;RuntimeConfig config_;Target target_{};std::uint64_t last_sequence_=0;State state_=State::Boot;Fault fault_=Fault::None;bool safety_alive_=false,joint_reference_=false,gripper_reference_=false,motion_allowed_=false,network_session_active_=false;std::string initialization_error_;FixedRing<500> recorder_;
};
}
