#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace ev3bench {

std::string trim(const std::string& value);
std::string read_file(const std::string& path);
void write_file(const std::string& path, const std::string& value);
std::int64_t monotonic_us();

class Attribute {
public:
    Attribute() = default;
    Attribute(const std::string& path, bool writable);
    ~Attribute();
    Attribute(Attribute&& other) noexcept;
    Attribute& operator=(Attribute&& other) noexcept;
    Attribute(const Attribute&) = delete;
    Attribute& operator=(const Attribute&) = delete;

    std::string read() const;
    int read_int() const;
    void write(const std::string& value) const;
    void write_int(int value) const;
    bool valid() const { return fd_ >= 0; }

private:
    int fd_ = -1;
    std::string path_;
};

struct MotorInfo {
    std::string path;
    std::string address;
    std::string driver;
    int count_per_rot = 0;
    int max_speed = 0;
    std::string commands;
    std::string stop_actions;
};

class MotorSysfs {
public:
    explicit MotorSysfs(const MotorInfo& info);

    const MotorInfo& info() const { return info_; }
    int position() const { return position_.read_int(); }
    int speed() const { return speed_.read_int(); }
    int duty_cycle() const { return duty_cycle_.read_int(); }
    std::string state() const { return state_.read(); }
    void set_duty(int duty) const { duty_cycle_sp_.write_int(duty); }
    void set_position_sp(int position) const { position_sp_.write_int(position); }
    void set_speed_sp(int speed) const { speed_sp_.write_int(speed); }
    void set_stop_action(const std::string& action) const { stop_action_.write(action); }
    void command(const std::string& command) const { command_.write(command); }
    void set_position(int position) const { position_rw_.write_int(position); }
    void stop(const std::string& action = "brake") const noexcept;

private:
    MotorInfo info_;
    Attribute position_;
    Attribute position_rw_;
    Attribute speed_;
    Attribute duty_cycle_;
    Attribute duty_cycle_sp_;
    Attribute position_sp_;
    Attribute speed_sp_;
    Attribute state_;
    Attribute stop_action_;
    Attribute command_;
};

std::vector<MotorInfo> discover_motors(const std::string& class_path);
MotorInfo find_motor(const std::vector<MotorInfo>& motors, const std::string& address);
int read_battery_uv(const std::string& power_supply_path);

}  // namespace ev3bench
