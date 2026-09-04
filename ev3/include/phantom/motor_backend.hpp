#pragma once
#include <array>
#include <cstdint>
#include <string>

namespace phantom {
struct MotorSample { std::int32_t encoder_count=0; float speed_counts_s=0; std::int16_t duty_permille=0; bool connected=false; };
struct IoSnapshot { std::array<MotorSample,4> motors{}; bool local_stop_pressed=true; bool gripper_home_pressed=false; std::uint16_t battery_mv=0; };
class MotorBackend {
public:
  virtual ~MotorBackend() = default;
  virtual bool initialize(std::string& error)=0;
  virtual IoSnapshot read() noexcept=0;
  virtual bool set_duty(std::size_t axis,std::int16_t duty_permille) noexcept=0;
  virtual void brake_all() noexcept=0;
};

class MockMotorBackend final : public MotorBackend {
public:
  bool initialize(std::string& error) override;
  IoSnapshot read() noexcept override { return io_; }
  bool set_duty(std::size_t axis,std::int16_t duty) noexcept override;
  void brake_all() noexcept override;
  void set_local_stop(bool pressed) { io_.local_stop_pressed=pressed; }
  const std::array<std::int16_t,4>& commanded_duty() const { return duty_; }
  std::uint64_t nonzero_writes() const { return nonzero_writes_; }
private:
  IoSnapshot io_{}; std::array<std::int16_t,4> duty_{}; std::uint64_t nonzero_writes_=0;
};

class Ev3SysfsBackend final : public MotorBackend {
public:
  Ev3SysfsBackend(std::string motor_class="/sys/class/tacho-motor",std::string sensor_class="/sys/class/lego-sensor",bool brake_during_initialize=true,std::uint8_t actuator_scope_mask=0x0f,bool require_local_stop=true,bool require_gripper_home=true);
  ~Ev3SysfsBackend() override; bool initialize(std::string& error) override; IoSnapshot read() noexcept override;
  bool set_duty(std::size_t axis,std::int16_t duty_permille) noexcept override; void brake_all() noexcept override;
private:
  struct Impl; Impl* impl_; std::string motor_class_,sensor_class_;bool brake_during_initialize_;std::uint8_t actuator_scope_mask_;bool require_local_stop_,require_gripper_home_;
};
}
