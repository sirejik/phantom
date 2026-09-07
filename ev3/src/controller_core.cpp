#include "phantom/controller_core.hpp"
#include <algorithm>
#include <cmath>
#include <cstdio>

namespace phantom {
namespace {
// The supervisor needs a moment to bind and send its first heartbeat. "Never
// seen yet" during that window is startup, not loss; after it, and after the
// first heartbeat ever arrives, loss is enforced on the configured timeout.
constexpr std::uint64_t kSafetyStartupGraceUs = 1500000;
constexpr std::uint64_t kStationarySpeedCountsPerSecond = 2;
}

ControllerCore::ControllerCore(MotorBackend& backend,const RuntimeConfig& config,EventLog* log)
  :backend_(backend),config_(config),log_(log),recorder_(config.flight_recorder_samples){}

void ControllerCore::set_safety_heartbeat_alive(bool alive) noexcept {
  if(alive) safety_ever_seen_=true;
  safety_alive_=alive;
}

bool ControllerCore::initialize(){
  initialization_error_.clear();
  if(!backend_.initialize(initialization_error_)){
    fault_=Fault::Config;fault_latched_=false;state_=State::SafeHold;motion_allowed_=false;backend_.brake_all();
    if(log_) log_->emit(0,"CONTROLLER_INIT_FAILED","CONTROLLER",{EventLog::text("detail",initialization_error_)});
    return false;
  }
  backend_.brake_all();
  motion_allowed_=false;
  if(config_.qualification_only&&config_.actuator_scope_mask==0){state_=State::Discovery;fault_=Fault::None;}
  else{state_=config_.commissioning_valid?State::ConnectedUnreferenced:State::SafeHold;fault_=config_.commissioning_valid?Fault::None:Fault::Config;}
  if(log_) log_->emit(0,"CONTROLLER_STARTED","CONTROLLER",
                      {EventLog::number("state",(std::uint16_t)state_),
                       EventLog::number("actuator_scope_mask",config_.actuator_scope_mask),
                       EventLog::number("safety_observation_mask",config_.safety_observation_mask),
                       EventLog::boolean("qualification_only",config_.qualification_only),
                       EventLog::number("flight_recorder_samples",recorder_.capacity())});
  return true;
}

bool ControllerCore::publish_target(const Target& t) noexcept {
  constexpr std::uint32_t mask=wire::kCommandMotionFlagsMotionEnable|wire::kCommandMotionFlagsHoldRequest|wire::kCommandMotionFlagsTrackingValid|wire::kCommandMotionFlagsGraspValid;
  if(t.sequence<=last_sequence_||t.sequence==0||!std::isfinite(t.grip)||t.grip<0||t.grip>1||(t.motion_flags&~mask))return false;
  for(float q:t.q)if(!std::isfinite(q)||q<-6.4f||q>6.4f)return false;
  target_=t;last_sequence_=t.sequence;return true;
}

bool ControllerCore::ready_predicates()const noexcept{
  return config_.commissioning_valid&&config_.measured_limits_complete&&config_.external_power_cut_tested&&
         safety_alive_&&joint_reference_&&gripper_reference_&&!fault_latched_&&!stop_latched_;
}

void ControllerCore::brake_and_disarm() noexcept {
  motion_allowed_=false;target_.motion_flags=0;backend_.brake_all();
}

void ControllerCore::enter(State next,Fault fault,const char* event_code) noexcept {
  const State previous=state_;const Fault previous_fault=fault_;
  state_=next;fault_=fault;
  if(log_&&(previous!=next||previous_fault!=fault))
    log_->emit_transition(snapshot_.monotonic_us,event_code,"CONTROLLER",(std::uint16_t)previous,(std::uint16_t)next,(std::uint16_t)fault,last_sequence_);
}

void ControllerCore::open_incident(std::uint64_t now_us,const char* reason) noexcept {
  if(incident_open_)return;
  incident_open_=true;incident_pending_=true;++incident_counter_;
  // Deterministic, non-secret correlation id: controller-local counter plus the
  // monotonic timestamp of the freeze.
  for(std::size_t i=0;i<8;++i)snapshot_.incident_id[i]=(std::uint8_t)((now_us>>(8*i))&0xff);
  for(std::size_t i=0;i<8;++i)snapshot_.incident_id[8+i]=(std::uint8_t)((incident_counter_>>(8*i))&0xff);
  if(log_){
    char hex[33];static const char digits[]="0123456789abcdef";
    for(std::size_t i=0;i<16;++i){hex[2*i]=digits[snapshot_.incident_id[i]>>4];hex[2*i+1]=digits[snapshot_.incident_id[i]&15];}
    hex[32]='\0';
    log_->set_incident(hex);
    log_->emit(now_us,"INCIDENT_OPENED","CONTROLLER",{EventLog::text("reason",reason),EventLog::number("frozen_samples",recorder_.size())});
  }
}

void ControllerCore::refresh_snapshot(std::uint64_t now_us,const IoSnapshot& io) noexcept {
  snapshot_.monotonic_us=now_us;
  snapshot_.state=(std::uint16_t)state_;
  snapshot_.fault_code=(std::uint16_t)fault_;
  snapshot_.battery_mv=io.battery_mv;
  snapshot_.grip_state=(std::uint16_t)wire::GripState::UNREFERENCED;
  snapshot_.loop_health_flags=loop_health_flags_;
  std::uint32_t flags=0;
  if(config_.commissioning_valid||config_.qualification_only)flags|=wire::kTelemetryStatusFlagsCommissioningBundleValid;
  if(local_stop_active_)flags|=wire::kTelemetryStatusFlagsLocalStopActive;
  if(safety_alive_)flags|=wire::kTelemetryStatusFlagsSafetySupervisorAlive;
  if(joint_reference_)flags|=wire::kTelemetryStatusFlagsJointReferenceValid;
  if(gripper_reference_)flags|=wire::kTelemetryStatusFlagsGripperReferenceValid;
  snapshot_.status_flags=flags;
  // Observation fields are canonical zero outside safety_observation_mask; a
  // zero there means N_A, never a measurement (§11.8).
  for(std::size_t axis=0;axis<3;++axis){
    const bool observed=(config_.safety_observation_mask&(1u<<axis))!=0;
    snapshot_.q_actual[axis]=observed?(float)io.motors[axis].encoder_count:0.0f;
    snapshot_.q_speed[axis]=observed?io.motors[axis].speed_counts_s:0.0f;
  }
  snapshot_.grip_actual=0.0f;
}

void ControllerCore::tick(std::uint64_t now,std::uint32_t dt)noexcept{
  if(first_tick_us_==0)first_tick_us_=now;
  const auto io=backend_.read();
  motors_stationary_=true;
  for(const auto& motor:io.motors)
    if(std::fabs(motor.speed_counts_s)>(float)kStationarySpeedCountsPerSecond)motors_stationary_=false;

  // --- Predicates that must hold on every stage, including scope 0x00 -------
  const std::uint64_t safe_hold_us=(std::uint64_t)config_.loop_safe_hold_ms*1000;
  const std::uint64_t fault_us=(std::uint64_t)config_.loop_fault_ms*1000;
  bool loop_safe_hold=false,loop_fault=false;
  if(dt>=25000)loop_health_flags_|=wire::kLoopHealthFlagsJitterOver25Ms;
  if(dt>=40000)loop_health_flags_|=wire::kLoopHealthFlagsSeriousOverrunOver40Ms;
  if(dt>fault_us){loop_fault=true;loop_health_flags_|=wire::kLoopHealthFlagsSafeHoldOverrunSeen;}
  else if(dt>safe_hold_us){loop_safe_hold=true;loop_health_flags_|=wire::kLoopHealthFlagsSafeHoldOverrunSeen;}
  if(log_&&log_->degraded())loop_health_flags_|=wire::kLoopHealthFlagsLoggerBackpressureSeen;

  const bool safety_grace=!safety_ever_seen_&&now-first_tick_us_<=kSafetyStartupGraceUs;
  const bool safety_lost=!safety_alive_&&!safety_grace;

  const bool stop_edge=io.local_stop_pressed&&!local_stop_active_;
  local_stop_active_=io.local_stop_pressed;
  if(io.local_stop_pressed&&!stop_latched_){
    stop_latched_=true;
    if(log_)log_->emit(now,"LOCAL_STOP","SAFETY",{EventLog::boolean("latched",true)});
  }
  (void)stop_edge;
  if(safety_lost&&!fault_latched_){
    // §7.24: supervisor loss is a latched STOPPED condition, not a soft hold.
    fault_latched_=true;
    if(log_)log_->emit(now,"SAFETY_PROCESS_LOST","SAFETY",{EventLog::number("timeout_ms",config_.heartbeat_timeout_ms)});
  }

  // --- State selection ------------------------------------------------------
  if(stop_latched_||fault_latched_){
    brake_and_disarm();
    const Fault latched=fault_latched_?(safety_lost||fault_==Fault::ControllerProcess?Fault::ControllerProcess:fault_):Fault::None;
    enter(State::Stopped,latched,"STOPPED");
    open_incident(now,stop_latched_?"local_stop":"latched_fault");
  }else if(loop_fault){
    brake_and_disarm();
    enter(State::SafeHold,Fault::LoopOverrun,"SAFE_HOLD");
  }else if(loop_safe_hold){
    brake_and_disarm();
    enter(State::SafeHold,Fault::None,"SAFE_HOLD");
  }else if(config_.qualification_only&&config_.actuator_scope_mask==0){
    // Network-only: no actuator authority at all, but liveness and loop health
    // above are still evaluated and observable.
    brake_and_disarm();
    enter(network_session_active_?State::ConnectedUnreferenced:State::Discovery,Fault::None,"NETWORK_ONLY");
  }else if(!ready_predicates()){
    brake_and_disarm();
    enter(fault_==Fault::None?State::ConnectedUnreferenced:State::SafeHold,fault_,"ADMISSION_BLOCKED");
  }else{
    const bool fresh=target_.received_us<=now&&(now-target_.received_us)<=(std::uint64_t)config_.command_timeout_ms*1000;
    const bool enabled=(target_.motion_flags&wire::kCommandMotionFlagsMotionEnable)&&
                       !(target_.motion_flags&wire::kCommandMotionFlagsHoldRequest)&&
                       (target_.motion_flags&wire::kCommandMotionFlagsTrackingValid);
    if(!fresh){brake_and_disarm();enter(State::SafeHold,Fault::Timeout,"SAFE_HOLD");}
    else if(!enabled){brake_and_disarm();enter(State::Hold,Fault::None,"HOLD");}
    else{motion_allowed_=true;enter(State::Tracking,Fault::None,"TRACKING");
      /* Stage 2 deliberately has no network-to-motor actuator law. */ backend_.brake_all();}
  }

  refresh_snapshot(now,io);
  if(!incident_open_){
    FlightSample sample;
    sample.monotonic_us=now;sample.command_sequence=last_sequence_;sample.loop_dt_us=dt;
    sample.state=state_;sample.fault=fault_;sample.status_flags=snapshot_.status_flags;
    sample.loop_health_flags=loop_health_flags_;sample.battery_mv=io.battery_mv;
    for(std::size_t i=0;i<4;++i){sample.encoder[i]=io.motors[i].encoder_count;sample.duty[i]=io.motors[i].duty_permille;}
    recorder_.push(sample);
  }
  if(log_)log_->flush();
}

RecoveryResult ControllerCore::request_reset_stopped() noexcept {
  if(!stop_latched_)return RecoveryResult::NotLatched;
  if(local_stop_active_)return RecoveryResult::StopStillEngaged;
  if(!motors_stationary_)return RecoveryResult::MotorsMoving;
  if(fault_latched_)return RecoveryResult::FaultStillLatched;
  stop_latched_=false;
  // Recovery never arms motion: the next state is chosen only by session and
  // reference validity, and the operator must re-arm deliberately (S9).
  motion_allowed_=false;
  incident_open_=false;
  if(log_)log_->emit(snapshot_.monotonic_us,"RESET_STOPPED_ACCEPTED","CONTROLLER",{});
  return RecoveryResult::Ok;
}

RecoveryResult ControllerCore::acknowledge_fault(std::uint16_t fault_code) noexcept {
  if(!fault_latched_)return RecoveryResult::NotLatched;
  if(fault_code!=(std::uint16_t)fault_)return RecoveryResult::FaultStillLatched;
  if(!safety_alive_)return RecoveryResult::FaultStillLatched;  // cause not objectively removed
  fault_latched_=false;fault_=Fault::None;motion_allowed_=false;incident_open_=false;
  if(log_)log_->emit(snapshot_.monotonic_us,"FAULT_ACK_ACCEPTED","CONTROLLER",{EventLog::number("fault_code",fault_code)});
  return RecoveryResult::Ok;
}

void ControllerCore::shutdown()noexcept{
  brake_and_disarm();
  if(!stop_latched_&&!fault_latched_)enter(State::SafeHold,fault_,"CONTROLLER_SHUTDOWN");
  if(log_){log_->emit(snapshot_.monotonic_us,"CONTROLLER_STOPPED","CONTROLLER",{EventLog::number("state",(std::uint16_t)state_)});log_->flush();}
}
}
