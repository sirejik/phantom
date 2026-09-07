#pragma once
#include "phantom/event_log.hpp"
#include "phantom/motor_backend.hpp"
#include "protocol_constants.hpp"
#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace phantom {
enum class State:std::uint16_t { Boot=(std::uint16_t)wire::State::BOOT,UserCalibration=(std::uint16_t)wire::State::USER_CALIBRATION,Discovery=(std::uint16_t)wire::State::DISCOVERY,ConnectedUnreferenced=(std::uint16_t)wire::State::CONNECTED_UNREFERENCED,RobotCalibration=(std::uint16_t)wire::State::ROBOT_CALIBRATION,Ready=(std::uint16_t)wire::State::READY,Hold=(std::uint16_t)wire::State::HOLD,Tracking=(std::uint16_t)wire::State::TRACKING,SafeHold=(std::uint16_t)wire::State::SAFE_HOLD,Stopped=(std::uint16_t)wire::State::STOPPED,Commissioning=(std::uint16_t)wire::State::COMMISSIONING };
enum class Fault:std::uint16_t { None=(std::uint16_t)wire::Fault::NONE,Timeout=(std::uint16_t)wire::Fault::FAULT_TIMEOUT,Config=(std::uint16_t)wire::Fault::FAULT_CONFIG,Limit=(std::uint16_t)wire::Fault::FAULT_LIMIT,JointStall=(std::uint16_t)wire::Fault::FAULT_JOINT_STALL,Gripper=(std::uint16_t)wire::Fault::FAULT_GRIPPER,Reference=(std::uint16_t)wire::Fault::FAULT_REFERENCE,Localization=(std::uint16_t)wire::Fault::FAULT_LOCALIZATION,ControllerProcess=(std::uint16_t)wire::Fault::FAULT_CONTROLLER_PROCESS,LoopOverrun=(std::uint16_t)wire::Fault::FAULT_LOOP_OVERRUN,Security=(std::uint16_t)wire::Fault::FAULT_SECURITY,MotorOverload=(std::uint16_t)wire::Fault::FAULT_MOTOR_OVERLOAD,Space=(std::uint16_t)wire::Fault::FAULT_SPACE,GripperHome=(std::uint16_t)wire::Fault::FAULT_GRIPPER_HOME,CollisionSet=(std::uint16_t)wire::Fault::FAULT_COLLISION_SET,PayloadProfile=(std::uint16_t)wire::Fault::FAULT_PAYLOAD_PROFILE,HoldOverload=(std::uint16_t)wire::Fault::FAULT_HOLD_OVERLOAD,BatteryLow=(std::uint16_t)wire::Fault::FAULT_BATTERY_LOW };

// Result of an operator recovery transaction (§4.7.5). The controller never
// re-arms motion as part of recovery; it only clears the blocking latch.
enum class RecoveryResult:std::uint16_t {
  Ok=(std::uint16_t)wire::ResultCode::OK,
  NotLatched=(std::uint16_t)wire::ResultCode::ERR_STATE,
  StopStillEngaged=(std::uint16_t)wire::ResultCode::ERR_STATE,
  MotorsMoving=(std::uint16_t)wire::ResultCode::ERR_STATE,
  FaultStillLatched=(std::uint16_t)wire::ResultCode::ERR_FAULT
};

struct Target { std::uint64_t sequence=0,received_us=0; std::uint32_t motion_flags=0; std::array<float,3> q{}; float grip=0; };

struct RuntimeConfig {
  std::uint32_t command_timeout_ms=120;
  std::uint32_t loop_safe_hold_ms=60;
  std::uint32_t loop_fault_ms=100;
  std::uint32_t heartbeat_timeout_ms=100;
  std::uint32_t flight_recorder_samples=500;
  bool commissioning_valid=false,measured_limits_complete=false,external_power_cut_tested=false,qualification_only=false;
  std::uint8_t actuator_scope_mask=0x0f,safety_observation_mask=0x0f;
  std::array<float,3> q_min{{0,0,0}},q_max{{0,0,0}},max_velocity{{0,0,0}};
};

struct FlightSample { std::uint64_t monotonic_us=0,command_sequence=0; std::uint32_t loop_dt_us=0,status_flags=0,loop_health_flags=0; State state=State::Boot; Fault fault=Fault::None; std::array<std::int32_t,4> encoder{}; std::array<std::int16_t,4> duty{}; std::uint16_t battery_mv=0; };

// Runtime-sized ring: §7.20.2 makes the depth configuration, not a compile-time
// constant, and the allocation happens once outside the control loop.
class FlightRing {
public:
  explicit FlightRing(std::size_t capacity):data_(capacity?capacity:1){}
  void push(const FlightSample& sample) noexcept { data_[head_]=sample;head_=(head_+1)%data_.size();if(size_<data_.size())++size_; }
  std::size_t size() const noexcept { return size_; }
  std::size_t capacity() const noexcept { return data_.size(); }
  const FlightSample& newest() const noexcept { return data_[(head_+data_.size()-1)%data_.size()]; }
  // Oldest-first access for incident export.
  const FlightSample& at(std::size_t index) const noexcept { return data_[(head_+data_.size()-size_+index)%data_.size()]; }
private:
  std::vector<FlightSample> data_;std::size_t head_=0,size_=0;
};

// Bounded snapshot the network worker serialises into wire TELEMETRY. The
// controller owns every field; `phantom-network` never synthesises state.
struct TelemetrySnapshot {
  std::uint64_t monotonic_us=0;
  std::uint16_t state=(std::uint16_t)wire::State::BOOT;
  std::uint16_t fault_code=0;
  std::uint32_t status_flags=0;
  std::uint16_t battery_mv=0;
  std::uint16_t grip_state=0;
  std::uint32_t loop_health_flags=0;
  std::array<std::uint8_t,16> incident_id{};
  std::array<float,3> q_actual{};
  std::array<float,3> q_speed{};
  float grip_actual=0;
};

class ControllerCore {
public:
  ControllerCore(MotorBackend& backend,const RuntimeConfig& config,EventLog* log=nullptr);
  bool initialize();
  void set_safety_heartbeat_alive(bool alive) noexcept;
  void set_references_valid(bool joints,bool gripper) noexcept { joint_reference_=joints;gripper_reference_=gripper; }
  void set_network_session_active(bool active) noexcept { network_session_active_=active; }
  bool publish_target(const Target& target) noexcept;
  void tick(std::uint64_t now_us,std::uint32_t dt_us) noexcept;
  void shutdown() noexcept;

  // Recovery transactions (§4.7.5). Neither arms motion.
  RecoveryResult request_reset_stopped() noexcept;
  RecoveryResult acknowledge_fault(std::uint16_t fault_code) noexcept;

  State state() const noexcept { return state_; }
  Fault fault() const noexcept { return fault_; }
  bool motion_allowed() const noexcept { return motion_allowed_; }
  bool stop_latched() const noexcept { return stop_latched_; }
  bool fault_latched() const noexcept { return fault_latched_; }
  const std::string& initialization_error() const noexcept { return initialization_error_; }
  const FlightRing& recorder() const noexcept { return recorder_; }
  const TelemetrySnapshot& snapshot() const noexcept { return snapshot_; }
  // Set when a latched incident froze the recorder and an export is owed.
  bool incident_pending() const noexcept { return incident_pending_; }
  void clear_incident_pending() noexcept { incident_pending_=false; }
  const std::array<std::uint8_t,16>& incident_id() const noexcept { return snapshot_.incident_id; }

private:
  void enter(State state,Fault fault,const char* event_code) noexcept;
  void brake_and_disarm() noexcept;
  bool ready_predicates() const noexcept;
  void open_incident(std::uint64_t now_us,const char* reason) noexcept;
  void refresh_snapshot(std::uint64_t now_us,const IoSnapshot& io) noexcept;

  MotorBackend& backend_;RuntimeConfig config_;EventLog* log_;
  Target target_{};std::uint64_t last_sequence_=0;
  State state_=State::Boot;Fault fault_=Fault::None;
  bool safety_alive_=false,safety_ever_seen_=false,joint_reference_=false,gripper_reference_=false;
  bool motion_allowed_=false,network_session_active_=false;
  bool stop_latched_=false,fault_latched_=false,local_stop_active_=false,motors_stationary_=true;
  bool incident_pending_=false,incident_open_=false;
  std::uint64_t first_tick_us_=0,incident_counter_=0;
  std::uint32_t loop_health_flags_=0;
  std::string initialization_error_;
  FlightRing recorder_;
  TelemetrySnapshot snapshot_;
};
}
