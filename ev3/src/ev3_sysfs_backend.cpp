#include "phantom/motor_backend.hpp"
#include <algorithm>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <fstream>
#include <sys/stat.h>
#include <unistd.h>
namespace phantom {
namespace {
std::string read_text(const std::string& path){std::ifstream file(path);std::string value;std::getline(file,value);return value;}
int open_attr(const std::string& path,int flags){return ::open(path.c_str(),flags|O_CLOEXEC);}
bool read_int_fd(int fd,int& value){if(fd<0)return false;char buffer[32]{};if(::lseek(fd,0,SEEK_SET)<0)return false;const auto length=::read(fd,buffer,sizeof(buffer)-1);if(length<=0)return false;char* end=nullptr;const long parsed=std::strtol(buffer,&end,10);if(end==buffer)return false;value=(int)parsed;return true;}
bool write_fd(int fd,const std::string& value){if(fd<0||::lseek(fd,0,SEEK_SET)<0)return false;return ::write(fd,value.data(),value.size())==(ssize_t)value.size();}
std::string port_name(std::string address){const auto separator=address.rfind(':');if(separator!=std::string::npos)address=address.substr(separator+1);std::transform(address.begin(),address.end(),address.begin(),::tolower);return address;}
}
struct Ev3SysfsBackend::Impl {
  struct Motor {int position=-1,speed=-1,duty=-1,stop_action=-1,command=-1;bool run_direct=false;};
  std::array<Motor,4> motors{};int local_stop=-1,gripper_home=-1,battery_uv=-1;bool ok=false;
};
Ev3SysfsBackend::Ev3SysfsBackend(std::string motor_class,std::string sensor_class,bool brake_init,std::uint8_t scope,bool require_stop,bool require_home):impl_(new Impl),motor_class_(std::move(motor_class)),sensor_class_(std::move(sensor_class)),brake_during_initialize_(brake_init),actuator_scope_mask_(scope&0x0f),require_local_stop_(require_stop),require_gripper_home_(require_home){}
Ev3SysfsBackend::~Ev3SysfsBackend(){if(brake_during_initialize_)brake_all();for(auto& motor:impl_->motors)for(int fd:{motor.position,motor.speed,motor.duty,motor.stop_action,motor.command})if(fd>=0)::close(fd);for(int fd:{impl_->local_stop,impl_->gripper_home,impl_->battery_uv})if(fd>=0)::close(fd);delete impl_;}
bool Ev3SysfsBackend::initialize(std::string& error){
  DIR* directory=::opendir(motor_class_.c_str());if(!directory){error=std::strerror(errno);return false;}
  dirent* entry;
  while((entry=::readdir(directory))){
    if(entry->d_name[0]=='.')continue;
    const std::string path=motor_class_+"/"+entry->d_name;
    const std::string address=port_name(read_text(path+"/address"));
    if(address.size()!=4||address.substr(0,3)!="out")continue;
    const int index=address[3]-'a';
    if(index<0||index>3)continue;
    const std::string expected=index==3?"lego-ev3-m-motor":"lego-ev3-l-motor";if(read_text(path+"/driver_name")!=expected||read_text(path+"/count_per_rot")!="360")continue;
    auto& motor=impl_->motors[index];motor.position=open_attr(path+"/position",O_RDONLY);motor.speed=open_attr(path+"/speed",O_RDONLY);motor.duty=open_attr(path+"/duty_cycle_sp",O_WRONLY);motor.stop_action=open_attr(path+"/stop_action",O_WRONLY);motor.command=open_attr(path+"/command",O_WRONLY);
  }
  ::closedir(directory);
  for(std::size_t index=0;index<4;++index){const auto& motor=impl_->motors[index];const bool complete=motor.position>=0&&motor.speed>=0&&motor.duty>=0&&motor.stop_action>=0&&motor.command>=0;if((actuator_scope_mask_&(1u<<index))&&!complete){error="required scoped motor missing/wrong type or count_per_rot != 360";brake_all();return false;}}
  directory=::opendir(sensor_class_.c_str());if(!directory&&(require_local_stop_||require_gripper_home_)){error="lego-sensor unavailable";brake_all();return false;}
  if(directory){
  while((entry=::readdir(directory))){
    if(entry->d_name[0]=='.')continue;
    const std::string path=sensor_class_+"/"+entry->d_name;
    if(read_text(path+"/driver_name")!="lego-ev3-touch")continue;
    const std::string address=port_name(read_text(path+"/address"));
    if(address=="in4")impl_->local_stop=open_attr(path+"/value0",O_RDONLY);else if(address=="in3")impl_->gripper_home=open_attr(path+"/value0",O_RDONLY);
  }
  ::closedir(directory);}
  if((require_local_stop_&&impl_->local_stop<0)||(require_gripper_home_&&impl_->gripper_home<0)){error="required LOCAL_STOP in4 or GRIPPER_HOME in3 missing/wrong type";brake_all();return false;}
  impl_->battery_uv=open_attr("/sys/class/power_supply/lego-ev3-battery/voltage_now",O_RDONLY);if(impl_->battery_uv<0){error="EV3 battery telemetry source missing";brake_all();return false;}
  impl_->ok=true;if(brake_during_initialize_)brake_all();error.clear();return true;
}
IoSnapshot Ev3SysfsBackend::read()noexcept{
  IoSnapshot io;io.local_stop_pressed=require_local_stop_;if(!impl_->ok)return io;
  for(std::size_t index=0;index<4;++index){int position=0,speed=0;const bool position_ok=read_int_fd(impl_->motors[index].position,position);const bool speed_ok=read_int_fd(impl_->motors[index].speed,speed);io.motors[index].connected=position_ok&&speed_ok;io.motors[index].encoder_count=position;io.motors[index].speed_counts_s=(float)speed;}
  int stop=1,home=0,battery_uv=0;if(impl_->local_stop>=0){const bool stop_ok=read_int_fd(impl_->local_stop,stop);io.local_stop_pressed=!stop_ok||stop!=0;}else io.local_stop_pressed=false;io.gripper_home_pressed=read_int_fd(impl_->gripper_home,home)&&home!=0;if(read_int_fd(impl_->battery_uv,battery_uv)&&battery_uv>0)io.battery_mv=(std::uint16_t)std::min(battery_uv/1000,65535);return io;
}
// ev3dev `duty_cycle_sp` is signed integer percent, so the protocol's permille
// resolution cannot be expressed on this hardware. The conversion is explicit,
// symmetric around zero and rounds to nearest so a small commanded duty is not
// silently truncated to standstill; the residual quantisation is a documented
// property of the pinned platform, not an accident of integer division.
std::int16_t Ev3SysfsBackend::permille_to_percent(std::int16_t duty_permille)noexcept{
  const std::int16_t clamped=std::max<std::int16_t>(-1000,std::min<std::int16_t>(1000,duty_permille));
  const int magnitude=(std::abs((int)clamped)+5)/10;
  return (std::int16_t)(clamped<0?-magnitude:magnitude);
}
bool Ev3SysfsBackend::set_duty(std::size_t axis,std::int16_t duty)noexcept{
  if(!impl_->ok||axis>=4||!(actuator_scope_mask_&(1u<<axis))||impl_->motors[axis].duty<0)return false;
  auto& motor=impl_->motors[axis];
  if(!write_fd(motor.duty,std::to_string(permille_to_percent(duty))))return false;
  // `run-direct` only has to be issued when entering the mode; re-issuing it on
  // every 50 Hz sample is a pointless sysfs write on a 300 MHz brick.
  if(motor.run_direct)return true;
  if(!write_fd(motor.command,"run-direct"))return false;
  motor.run_direct=true;return true;
}
void Ev3SysfsBackend::brake_all()noexcept{for(auto& motor:impl_->motors){if(motor.duty>=0)write_fd(motor.duty,"0");if(motor.stop_action>=0)write_fd(motor.stop_action,"brake");if(motor.command>=0)write_fd(motor.command,"stop");motor.run_direct=false;}}
}
