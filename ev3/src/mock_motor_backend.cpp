#include "phantom/motor_backend.hpp"
#include <algorithm>
namespace phantom {
bool MockMotorBackend::initialize(std::string& error){error.clear();for(auto& m:io_.motors)m.connected=true;io_.local_stop_pressed=false;brake_all();return true;}
bool MockMotorBackend::set_duty(std::size_t axis,std::int16_t duty)noexcept{if(axis>=4)return false;duty=std::max<std::int16_t>(-1000,std::min<std::int16_t>(1000,duty));duty_[axis]=duty;io_.motors[axis].duty_permille=duty;if(duty)++nonzero_writes_;return true;}
void MockMotorBackend::brake_all()noexcept{for(std::size_t i=0;i<4;++i){duty_[i]=0;io_.motors[i].duty_permille=0;}}
}
