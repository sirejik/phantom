#include "ev3_bench/sysfs.hpp"

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <memory>
#include <stdexcept>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

namespace ev3bench {
namespace {

std::runtime_error io_error(const std::string& operation, const std::string& path) {
    return std::runtime_error(operation + " " + path + ": " + std::strerror(errno));
}

int parse_int(const std::string& text, const std::string& path) {
    try {
        return std::stoi(trim(text));
    } catch (...) {
        throw std::runtime_error("invalid integer in " + path + ": " + text);
    }
}

bool directory_exists(const std::string& path) {
    struct stat st {};
    return ::stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
}

std::string normalize_address(std::string value) {
    value = trim(value);
    const auto pos = value.rfind(':');
    if (pos != std::string::npos) value = value.substr(pos + 1);
    std::transform(value.begin(), value.end(), value.begin(), ::tolower);
    return value;
}

}  // namespace

std::string trim(const std::string& value) {
    const auto begin = value.find_first_not_of(" \t\r\n");
    if (begin == std::string::npos) return {};
    return value.substr(begin, value.find_last_not_of(" \t\r\n") - begin + 1);
}

std::string read_file(const std::string& path) {
    const int fd = ::open(path.c_str(), O_RDONLY | O_CLOEXEC);
    if (fd < 0) throw io_error("open", path);
    char buffer[4096];
    const ssize_t size = ::read(fd, buffer, sizeof(buffer));
    const int saved_errno = errno;
    ::close(fd);
    errno = saved_errno;
    if (size < 0) throw io_error("read", path);
    return trim(std::string(buffer, static_cast<std::size_t>(size)));
}

void write_file(const std::string& path, const std::string& value) {
    const int fd = ::open(path.c_str(), O_WRONLY | O_CLOEXEC);
    if (fd < 0) throw io_error("open", path);
    const ssize_t size = ::write(fd, value.data(), value.size());
    const int saved_errno = errno;
    ::close(fd);
    errno = saved_errno;
    if (size != static_cast<ssize_t>(value.size())) throw io_error("write", path);
}

std::int64_t monotonic_us() {
    struct timespec value {};
#ifdef CLOCK_MONOTONIC_RAW
    const clockid_t clock_id = CLOCK_MONOTONIC_RAW;
#else
    const clockid_t clock_id = CLOCK_MONOTONIC;
#endif
    if (::clock_gettime(clock_id, &value) != 0) throw io_error("clock_gettime", "monotonic clock");
    return static_cast<std::int64_t>(value.tv_sec) * 1000000LL + value.tv_nsec / 1000;
}

Attribute::Attribute(const std::string& path, bool writable) : path_(path) {
    // ev3dev exposes several command attributes (notably `command`) as
    // write-only sysfs files. O_RDWR is rejected even for root, while no
    // writable Attribute needs to be read by this wrapper.
    fd_ = ::open(path.c_str(), (writable ? O_WRONLY : O_RDONLY) | O_CLOEXEC);
    if (fd_ < 0) throw io_error("open", path);
}

Attribute::~Attribute() {
    if (fd_ >= 0) ::close(fd_);
}

Attribute::Attribute(Attribute&& other) noexcept : fd_(other.fd_), path_(std::move(other.path_)) {
    other.fd_ = -1;
}

Attribute& Attribute::operator=(Attribute&& other) noexcept {
    if (this != &other) {
        if (fd_ >= 0) ::close(fd_);
        fd_ = other.fd_;
        path_ = std::move(other.path_);
        other.fd_ = -1;
    }
    return *this;
}

std::string Attribute::read() const {
    if (::lseek(fd_, 0, SEEK_SET) < 0) throw io_error("lseek", path_);
    char buffer[1024];
    const ssize_t size = ::read(fd_, buffer, sizeof(buffer));
    if (size < 0) throw io_error("read", path_);
    return trim(std::string(buffer, static_cast<std::size_t>(size)));
}

int Attribute::read_int() const { return parse_int(read(), path_); }

void Attribute::write(const std::string& value) const {
    if (::lseek(fd_, 0, SEEK_SET) < 0) throw io_error("lseek", path_);
    if (::write(fd_, value.data(), value.size()) != static_cast<ssize_t>(value.size())) {
        throw io_error("write", path_);
    }
}

void Attribute::write_int(int value) const { write(std::to_string(value)); }

MotorSysfs::MotorSysfs(const MotorInfo& info)
    : info_(info),
      position_(info.path + "/position", false),
      position_rw_(info.path + "/position", true),
      speed_(info.path + "/speed", false),
      duty_cycle_(info.path + "/duty_cycle", false),
      duty_cycle_sp_(info.path + "/duty_cycle_sp", true),
      position_sp_(info.path + "/position_sp", true),
      speed_sp_(info.path + "/speed_sp", true),
      state_(info.path + "/state", false),
      stop_action_(info.path + "/stop_action", true),
      command_(info.path + "/command", true) {}

void MotorSysfs::stop(const std::string& action) const noexcept {
    try { duty_cycle_sp_.write_int(0); } catch (...) {}
    try { stop_action_.write(action); } catch (...) {}
    try { command_.write("stop"); } catch (...) {}
}

std::vector<MotorInfo> discover_motors(const std::string& class_path) {
    DIR* dir = ::opendir(class_path.c_str());
    if (!dir) throw io_error("opendir", class_path);
    std::vector<MotorInfo> result;
    while (dirent* entry = ::readdir(dir)) {
        const std::string name(entry->d_name);
        if (name == "." || name == "..") continue;
        const std::string path = class_path + "/" + name;
        if (!directory_exists(path)) continue;
        try {
            MotorInfo info;
            info.path = path;
            info.address = read_file(path + "/address");
            info.driver = read_file(path + "/driver_name");
            info.count_per_rot = parse_int(read_file(path + "/count_per_rot"), path + "/count_per_rot");
            info.max_speed = parse_int(read_file(path + "/max_speed"), path + "/max_speed");
            info.commands = read_file(path + "/commands");
            info.stop_actions = read_file(path + "/stop_actions");
            result.push_back(std::move(info));
        } catch (...) {
            // Ignore transient, incomplete sysfs nodes and continue discovery.
        }
    }
    ::closedir(dir);
    std::sort(result.begin(), result.end(), [](const MotorInfo& a, const MotorInfo& b) {
        return a.address < b.address;
    });
    return result;
}

MotorInfo find_motor(const std::vector<MotorInfo>& motors, const std::string& address) {
    const std::string wanted = normalize_address(address);
    for (const auto& motor : motors) {
        if (normalize_address(motor.address) == wanted) return motor;
    }
    throw std::runtime_error("no motor with sysfs address matching " + address);
}

int read_battery_uv(const std::string& power_supply_path) {
    // The benchmark calls this every tick. Locate and open the attribute once so
    // battery telemetry does not silently reintroduce open/read/close jitter.
    static std::string cached_root;
    static std::unique_ptr<Attribute> cached_voltage;
    if (cached_root != power_supply_path) {
        cached_root = power_supply_path;
        cached_voltage.reset();
        DIR* dir = ::opendir(power_supply_path.c_str());
        if (!dir) return 0;
        while (dirent* entry = ::readdir(dir)) {
            const std::string name(entry->d_name);
            if (name == "." || name == "..") continue;
            for (const char* attribute : {"voltage_now", "voltage_avg"}) {
                try {
                    cached_voltage.reset(new Attribute(power_supply_path + "/" + name + "/" + attribute, false));
                    break;
                } catch (...) {}
            }
            if (cached_voltage) break;
        }
        ::closedir(dir);
    }
    if (!cached_voltage) return 0;
    try { return cached_voltage->read_int(); } catch (...) { return 0; }
}

}  // namespace ev3bench
