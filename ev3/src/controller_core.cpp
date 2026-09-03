#include "phantom/controller_core.hpp"
#include <algorithm>
#include <cmath>
namespace phantom {
bool ControllerCore::initialize(){std::string error;if(!backend_.initialize(error)){safe(State::SafeHold,Fault::Config);return false;}backend_.brake_all();motion_allowed_=false;state_=config_.commissioning_valid?State::ConnectedUnreferenced:State::SafeHold;fault_=config_.commissioning_valid?Fault::None:Fault::Config;return config_.commissioning_valid;}
bool ControllerCore::publish_target(const Target& t){if(t.sequence<=last_sequence_||t.sequence==0||!std::isfinite(t.grip)||t.grip<0||t.grip>1||t.motion_flags&~15u)return false;for(float q:t.q)if(!std::isfinite(q)||q<-6.4f||q>6.4f)return false;target_=t;last_sequence_=t.sequence;return true;}
bool ControllerCore::ready_predicates()const noexcept{return config_.commissioning_valid&&config_.measured_limits_complete&&config_.external_power_cut_tested&&safety_alive_&&joint_reference_&&gripper_reference_&&fault_==Fault::None;}
void ControllerCore::safe(State s,Fault f)noexcept{motion_allowed_=false;state_=s;if(f!=Fault::None)fault_=f;target_.motion_flags=0;backend_.brake_all();}
void ControllerCore::tick(std::uint64_t now,std::uint32_t dt)noexcept{
  const auto io=backend_.read();if(io.local_stop_pressed){safe(State::Stopped);}
  else if(!safety_alive_){safe(State::SafeHold,Fault::ControllerProcess);}
  else if(dt>100000){safe(State::SafeHold,Fault::LoopOverrun);}
  else if(!ready_predicates()){safe(fault_==Fault::None?State::ConnectedUnreferenced:State::SafeHold);}
  else {const bool fresh=target_.received_us<=now&&(now-target_.received_us)<=std::uint64_t(config_.command_timeout_ms)*1000;const bool enabled=(target_.motion_flags&1u)&&!(target_.motion_flags&2u)&&(target_.motion_flags&4u);if(!fresh)safe(State::SafeHold,Fault::Timeout);else if(!enabled)safe(State::Hold);else{motion_allowed_=true;state_=State::Tracking;/* Stage 2 deliberately has no network-to-motor actuator law. */backend_.brake_all();}}
  FlightSample sample;sample.monotonic_us=now;sample.command_sequence=last_sequence_;sample.loop_dt_us=dt;sample.state=state_;sample.fault=fault_;for(std::size_t i=0;i<4;++i){sample.encoder[i]=io.motors[i].encoder_count;sample.duty[i]=io.motors[i].duty_permille;}recorder_.push(sample);
}
void ControllerCore::shutdown()noexcept{safe(State::SafeHold);}
}
