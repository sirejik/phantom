#include "ev3_bench/sysfs.hpp"

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cmath>
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <fstream>
#include <functional>
#include <fcntl.h>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <sys/prctl.h>
#include <sys/types.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>
#include <vector>

#ifdef __GLIBC__
#include <gnu/libc-version.h>
#endif

using ev3bench::MotorInfo;
using ev3bench::MotorSysfs;

namespace {

std::atomic<bool> g_stop(false);
thread_local std::int64_t g_previous_work_us = 0;

void signal_handler(int) { g_stop.store(true); }

struct Options {
    std::string test;
    std::string motor_class = "/sys/class/tacho-motor";
    std::string power_supply = "/sys/class/power_supply";
    std::string output = "results/ev3/raw";
    // E0 on the current bench measured Medium=outA and Large=outB. These are
    // only defaults; discovery still verifies the actual driver_name.
    std::string large_address = "outB";
    std::string medium_address = "outA";
    std::string motor = "all";
    std::string mode = "all";
    std::string fault = "sigkill";
    std::string run_id;
    double duration = -1.0;
    int rate = 0;
    int heartbeat_ms = 100;
    int medium_static_ff = 0;
    int large_static_ff = 0;
    int controller_limit = 50;
    double controller_kp = 0.25;
    double controller_kd = 0.004;
    int settle_deadband = 3;
    bool arm = false;
    bool spin_only = false;
    bool stall_fixture = false;
    bool crash_ack = false;
    bool manual_e0 = false;
};

std::string usage() {
    return
        "Usage: ev3-bench TEST [options]\n"
        "TEST: smoke, e0..e13, c1..c7, d1..d8, e1_5, e1_minimal (e11 is analysis-only)\n"
        "Options:\n"
        "  --arm                    explicitly enable motor motion\n"
        "  --spin-only              E12: omit the stationary phase and run only the free-spin phase\n"
        "  --stall-fixture          confirm E7 beam + fixed soft stop is installed\n"
        "  --crash-ack              confirm E9 free shaft and <=20% crash test\n"
        "  --large-address outA     select by sysfs address, never motorN\n"
        "  --medium-address outD\n"
        "  --motor large|medium|all\n"
        "  --output DIR             raw log directory\n"
        "  --duration SEC           shorten/extend phases for diagnostics\n"
        "  --rate HZ                restrict E1/E3/E12 cadence\n"
        "  --mode naive|persistent|all\n"
        "  --fault sigterm|sigkill|sigstop|abort|baseline (E9)\n"
        "  --heartbeat-ms N         E9 stale heartbeat threshold\n"
        "  --medium-static-ff N     C2/C4/C5 static-friction feed-forward for outA\n"
        "  --large-static-ff N      C2/C4 static-friction feed-forward for outB\n"
        "  --controller-kp N --controller-kd N --controller-limit N --settle-deadband N\n"
        "  --manual-e0              interactive one-revolution/reset encoder check\n"
        "  --motor-class PATH       fake-sysfs/testing override\n"
        "  --power-supply PATH\n";
}

Options parse_args(int argc, char** argv) {
    if (argc < 2) throw std::runtime_error(usage());
    Options options;
    options.test = argv[1];
    for (int i = 2; i < argc; ++i) {
        const std::string arg(argv[i]);
        auto value = [&]() -> std::string {
            if (++i >= argc) throw std::runtime_error("missing value for " + arg);
            return argv[i];
        };
        if (arg == "--arm") options.arm = true;
        else if (arg == "--spin-only") options.spin_only = true;
        else if (arg == "--stall-fixture") options.stall_fixture = true;
        else if (arg == "--crash-ack") options.crash_ack = true;
        else if (arg == "--manual-e0") options.manual_e0 = true;
        else if (arg == "--large-address") options.large_address = value();
        else if (arg == "--medium-address") options.medium_address = value();
        else if (arg == "--motor") options.motor = value();
        else if (arg == "--output") options.output = value();
        else if (arg == "--duration") options.duration = std::stod(value());
        else if (arg == "--rate") options.rate = std::stoi(value());
        else if (arg == "--mode") options.mode = value();
        else if (arg == "--fault") options.fault = value();
        else if (arg == "--heartbeat-ms") options.heartbeat_ms = std::stoi(value());
        else if (arg == "--medium-static-ff") options.medium_static_ff = std::stoi(value());
        else if (arg == "--large-static-ff") options.large_static_ff = std::stoi(value());
        else if (arg == "--controller-kp") options.controller_kp = std::stod(value());
        else if (arg == "--controller-kd") options.controller_kd = std::stod(value());
        else if (arg == "--controller-limit") options.controller_limit = std::stoi(value());
        else if (arg == "--settle-deadband") options.settle_deadband = std::stoi(value());
        else if (arg == "--motor-class") options.motor_class = value();
        else if (arg == "--power-supply") options.power_supply = value();
        else if (arg == "--run-id") options.run_id = value();
        else if (arg == "--help" || arg == "-h") throw std::runtime_error(usage());
        else throw std::runtime_error("unknown option: " + arg + "\n" + usage());
    }
    if (options.run_id.empty()) options.run_id = std::to_string(ev3bench::monotonic_us());
    return options;
}

void mkdir_p(const std::string& path) {
    if (path.empty()) return;
    std::string current;
    if (path[0] == '/') current = "/";
    std::stringstream parts(path);
    std::string part;
    while (std::getline(parts, part, '/')) {
        if (part.empty()) continue;
        if (!current.empty() && current.back() != '/') current += '/';
        current += part;
        if (::mkdir(current.c_str(), 0755) != 0 && errno != EEXIST) {
            throw std::runtime_error("mkdir " + current + ": " + std::strerror(errno));
        }
    }
}

std::string csv_escape(const std::string& value) {
    if (value.find_first_of(",\"\r\n") == std::string::npos) return value;
    std::string escaped = "\"";
    for (char c : value) escaped += c == '\"' ? "\"\"" : std::string(1, c);
    return escaped + "\"";
}

std::string json_escape(const std::string& value) {
    std::string result;
    for (char c : value) {
        switch (c) {
            case '\\': result += "\\\\"; break;
            case '\"': result += "\\\""; break;
            case '\n': result += "\\n"; break;
            case '\r': result += "\\r"; break;
            case '\t': result += "\\t"; break;
            default: result += c;
        }
    }
    return result;
}

std::vector<std::string> directory_entries(const std::string& path) {
    std::vector<std::string> result;
    DIR* dir = ::opendir(path.c_str());
    if (!dir) return result;
    while (dirent* entry = ::readdir(dir)) {
        const std::string name(entry->d_name);
        if (name != "." && name != "..") result.push_back(name);
    }
    ::closedir(dir);
    std::sort(result.begin(), result.end());
    return result;
}

struct Row {
    std::int64_t time_us = 0;
    std::string test_id;
    std::string run_id;
    std::string address;
    std::string driver;
    int battery_uv = 0;
    std::string command_mode;
    int duty_sp = 0;
    int duty = 0;
    int position = 0;
    int speed = 0;
    std::string state;
    std::int64_t loop_dt_us = 0;
    double target_position = 0;
    double position_error = 0;
    double goal_position = 0;
    std::string event;
    std::string fault;
    int target_speed = 0;
    std::int64_t cpu_time_us = 0;
    std::int64_t heartbeat_age_us = 0;
    std::int64_t detection_latency_us = 0;
    std::int64_t stop_command_latency_us = 0;
    std::int64_t work_time_us = 0;
    double rate_hz = 0;
    std::string operation;
    std::int64_t operation_duration_us = 0;
    std::int64_t tick_start_us = 0;
    int trial_index = -1;
    int cycle_index = -1;
    int started_100ms = -1;
    int started_200ms = -1;
    int started_300ms = -1;
    int started_500ms = -1;
};

// D1--D8 keep their 50 Hz critical section intentionally small.  These
// samples are fixed-size and are rendered to CSV only after the motors stop.
struct FastTick {
    std::int64_t time_us = 0, dt_us = 0, work_us = 0, cpu_us = 0;
    int medium_position = 0, medium_speed = 0, medium_duty = 0, medium_actual_duty = 0;
    int large_position = 0, large_speed = 0, large_duty = 0, large_actual_duty = 0;
    int battery_uv = 0, trial = -1, cycle = -1;
    double medium_target = 0, large_target = 0;
    const char* event = "tick";
};

struct DualCommand {
    int medium_duty = 0, large_duty = 0;
    double medium_target = 0, large_target = 0;
    int trial = -1, cycle = -1;
    const char* event = "tick";
};

std::int64_t process_cpu_us() {
    struct timespec value {};
    if (::clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &value) != 0) return 0;
    return static_cast<std::int64_t>(value.tv_sec) * 1000000LL + value.tv_nsec / 1000;
}

class CsvLog {
public:
    explicit CsvLog(const std::string& path, bool periodic_flush = true) : path_(path), periodic_flush_(periodic_flush) {
        struct stat existing {};
        if (::stat(path.c_str(), &existing) == 0 && existing.st_size > 0) return;
        buffer_ = "monotonic_time_us,test_id,run_id,motor_address,motor_driver,battery_voltage,"
                  "command_mode,duty_cycle_sp,duty_cycle,position,speed,state_flags,loop_dt_us,"
                  "target_position,position_error,goal_position,event,fault,target_speed,cpu_time_us,"
                  "heartbeat_age_us,detection_latency_us,stop_command_latency_us,work_time_us,rate_hz,operation,operation_duration_us,tick_start_us,trial_index,cycle_index,started_100ms,started_200ms,started_300ms,started_500ms\n";
    }
    ~CsvLog() { try { flush(); } catch (...) {} }
    void row(const Row& r) {
        std::ostringstream line;
        line << r.time_us << ',' << csv_escape(r.test_id) << ',' << csv_escape(r.run_id) << ','
             << csv_escape(r.address) << ',' << csv_escape(r.driver) << ','
             << std::fixed << std::setprecision(6) << r.battery_uv / 1000000.0 << ','
             << csv_escape(r.command_mode) << ',' << r.duty_sp << ',' << r.duty << ','
             << r.position << ',' << r.speed << ',' << csv_escape(r.state) << ',' << r.loop_dt_us << ','
             << std::setprecision(3) << r.target_position << ',' << r.position_error << ',' << r.goal_position << ','
             << csv_escape(r.event) << ',' << csv_escape(r.fault) << ',' << r.target_speed << ',' << r.cpu_time_us << ','
             << r.heartbeat_age_us << ',' << r.detection_latency_us << ',' << r.stop_command_latency_us << ','
             << r.work_time_us << ',' << r.rate_hz << ',' << csv_escape(r.operation) << ',' << r.operation_duration_us << ',' << r.tick_start_us << ','
             << r.trial_index << ',' << r.cycle_index << ',' << r.started_100ms << ',' << r.started_200ms << ',' << r.started_300ms << ',' << r.started_500ms << '\n';
        buffer_ += line.str();
        if (!last_flush_us_) last_flush_us_ = r.time_us;
        if (periodic_flush_ && r.time_us - last_flush_us_ >= kFlushIntervalUs) flush();
    }
    void flush() {
        if (buffer_.empty()) return;
        std::ofstream out(path_, std::ios::binary | std::ios::app);
        if (!out) throw std::runtime_error("cannot create log " + path_);
        out << buffer_;
        if (!out) throw std::runtime_error("cannot write log " + path_);
        buffer_.clear();
        last_flush_us_ = ev3bench::monotonic_us();
    }
private:
    static constexpr std::int64_t kFlushIntervalUs = 1000000;
    std::string path_;
    std::string buffer_;
    std::int64_t last_flush_us_ = 0;
    bool periodic_flush_ = true;
};

class StopGuard {
public:
    explicit StopGuard(std::vector<MotorSysfs*> motors) : motors_(std::move(motors)) {}
    ~StopGuard() { stop(); }
    void stop() noexcept { for (auto* motor : motors_) motor->stop("brake"); }
private:
    std::vector<MotorSysfs*> motors_;
};

void sleep_seconds(double seconds) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::microseconds(
        static_cast<long long>(seconds * 1000000));
    while (!g_stop.load() && std::chrono::steady_clock::now() < deadline) {
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
}

void require_motion(const Options& options, const std::string& extra = {}) {
    if (!options.arm) {
        throw std::runtime_error("motion refused: disconnect any arm/load, fit only a short light pointer, then pass --arm");
    }
    if (extra == "stall" && !options.stall_fixture) {
        throw std::runtime_error("E7 refused: install a short LEGO lever and fixed soft stop, then pass --stall-fixture");
    }
    if (extra == "crash" && !options.crash_ack) {
        throw std::runtime_error("E9 refused: free shaft, duty <=20%, external reach to the EV3, then pass --crash-ack");
    }
}

void preflight_stop(const std::vector<MotorSysfs*>& motors) {
    for (auto* motor : motors) motor->stop("brake");
    std::this_thread::sleep_for(std::chrono::milliseconds(150));
    for (auto* motor : motors) {
        if (std::abs(motor->duty_cycle()) != 0) {
            throw std::runtime_error("preflight failed: non-zero duty on " + motor->info().address);
        }
    }
}

Row sample(const std::string& test, const std::string& run_id, const MotorSysfs& motor,
           const Options& options, const std::string& mode, int duty_sp, std::int64_t dt,
           double target = 0, const std::string& event = {}, const std::string& fault = {},
           int observed_position = std::numeric_limits<int>::min(),
           int observed_speed = std::numeric_limits<int>::min()) {
    Row r;
    r.time_us = ev3bench::monotonic_us(); r.test_id = test; r.run_id = run_id;
    r.address = motor.info().address; r.driver = motor.info().driver;
    r.battery_uv = ev3bench::read_battery_uv(options.power_supply); r.command_mode = mode;
    r.duty_sp = duty_sp; r.duty = motor.duty_cycle();
    r.position = observed_position == std::numeric_limits<int>::min() ? motor.position() : observed_position;
    r.speed = observed_speed == std::numeric_limits<int>::min() ? motor.speed() : observed_speed;
    r.state = motor.state(); r.loop_dt_us = dt;
    r.target_position = target; r.position_error = target - r.position;
    r.goal_position = target;
    r.event = event; r.fault = fault;
    r.cpu_time_us = process_cpu_us();
    r.work_time_us = g_previous_work_us;
    return r;
}

template <typename Callback>
void cadence_loop(double seconds, double rate, Callback callback) {
    if (rate <= 0) throw std::runtime_error("cadence rate must be positive");
    const auto period = std::chrono::microseconds(static_cast<long long>(1000000.0 / rate));
    auto next = std::chrono::steady_clock::now();
    const auto end = next + std::chrono::microseconds(static_cast<long long>(seconds * 1000000));
    std::int64_t last_us = ev3bench::monotonic_us();
    g_previous_work_us = 0;
    while (!g_stop.load() && std::chrono::steady_clock::now() < end) {
        const std::int64_t now_us = ev3bench::monotonic_us();
        const std::int64_t work_start = now_us;
        callback(now_us - last_us);
        g_previous_work_us = ev3bench::monotonic_us() - work_start;
        last_us = now_us;
        next += period;
        std::this_thread::sleep_until(next);
    }
}

std::string rate_label(double rate) {
    std::ostringstream out;
    out << std::fixed << std::setprecision(rate == std::floor(rate) ? 0 : 3) << rate;
    std::string value = out.str();
    std::replace(value.begin(), value.end(), '.', '_');
    return value;
}

std::string log_path(const Options& o, const std::string& suffix) {
    return o.output + "/" + o.test + "_" + o.run_id + "_" + suffix + ".csv";
}

class BatterySampler {
public:
    explicit BatterySampler(const Options& options) : options_(options) {
        worker_ = std::thread([this] {
            while (!done_.load()) {
                voltage_.store(ev3bench::read_battery_uv(options_.power_supply));
                for (int i = 0; i < 10 && !done_.load(); ++i) std::this_thread::sleep_for(std::chrono::milliseconds(10));
            }
        });
    }
    ~BatterySampler() { done_.store(true); if (worker_.joinable()) worker_.join(); }
    int voltage() const { return voltage_.load(); }
private:
    Options options_;
    std::atomic<bool> done_{false};
    std::atomic<int> voltage_{0};
    std::thread worker_;
};

class ActiveSafetySupervisor {
public:
    ActiveSafetySupervisor(MotorSysfs& medium, MotorSysfs& large) : medium_(medium), large_(large) {
        worker_ = std::thread([this] {
            while (!done_.load()) {
                if (g_stop.load() || ev3bench::monotonic_us() - heartbeat_us_.load() > 250000) {
                    medium_.stop("brake"); large_.stop("brake");
                    tripped_.store(true); return;
                }
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
            }
        });
    }
    ~ActiveSafetySupervisor() { done_.store(true); if (worker_.joinable()) worker_.join(); }
    void heartbeat() { heartbeat_us_.store(ev3bench::monotonic_us()); }
    bool tripped() const { return tripped_.load(); }
private:
    MotorSysfs& medium_; MotorSysfs& large_;
    std::atomic<bool> done_{false}, tripped_{false};
    std::atomic<std::int64_t> heartbeat_us_{ev3bench::monotonic_us()};
    std::thread worker_;
};

template <typename Controller>
std::vector<FastTick> active_dual_loop(const Options& o, MotorSysfs& medium, MotorSysfs& large,
                                       double seconds, Controller controller, bool read_actual = false) {
    const int rate = o.rate ? o.rate : 50;
    const auto period = std::chrono::microseconds(1000000 / rate);
    std::vector<FastTick> ticks; ticks.reserve(static_cast<std::size_t>(seconds * rate + 4));
    BatterySampler battery(o);
    ActiveSafetySupervisor safety(medium, large);
    medium.command("run-direct"); large.command("run-direct");
    auto next = std::chrono::steady_clock::now(), end = next + std::chrono::microseconds(static_cast<long long>(seconds * 1000000));
    std::int64_t last = ev3bench::monotonic_us();
    while (!g_stop.load() && !safety.tripped() && std::chrono::steady_clock::now() < end) {
        const std::int64_t start = ev3bench::monotonic_us();
        const int mp = medium.position(), ms = medium.speed(), lp = large.position(), ls = large.speed();
        const double elapsed = ticks.empty() ? 0.0 : (start - ticks.front().time_us) / 1000000.0;
        const DualCommand c = controller(elapsed, mp, ms, lp, ls);
        medium.set_duty(c.medium_duty); large.set_duty(c.large_duty);
        FastTick t; t.time_us = start; t.dt_us = start - last; t.cpu_us = process_cpu_us();
        t.medium_position = mp; t.medium_speed = ms; t.large_position = lp; t.large_speed = ls;
        t.medium_duty = c.medium_duty; t.large_duty = c.large_duty;
        t.medium_actual_duty = read_actual ? medium.duty_cycle() : c.medium_duty;
        t.large_actual_duty = read_actual ? large.duty_cycle() : c.large_duty;
        t.battery_uv = battery.voltage(); t.medium_target = c.medium_target; t.large_target = c.large_target;
        t.trial = c.trial; t.cycle = c.cycle; t.event = c.event;
        safety.heartbeat(); t.work_us = ev3bench::monotonic_us() - start; ticks.push_back(t); last = start;
        next += period; std::this_thread::sleep_until(next);
    }
    medium.stop("brake"); large.stop("brake");
    return ticks;
}

void write_dual_ticks(const Options& o, const std::string& suffix, const std::vector<FastTick>& ticks, MotorSysfs& medium, MotorSysfs& large) {
    CsvLog log(log_path(o, suffix), false);
    auto emit = [&](const FastTick& t, MotorSysfs& motor, bool is_medium) {
        Row r; r.time_us = t.time_us; r.test_id = o.test; r.run_id = o.run_id;
        r.address = motor.info().address; r.driver = motor.info().driver; r.battery_uv = t.battery_uv;
        r.command_mode = "run-direct"; r.duty_sp = is_medium ? t.medium_duty : t.large_duty;
        r.duty = is_medium ? t.medium_actual_duty : t.large_actual_duty;
        r.position = is_medium ? t.medium_position : t.large_position; r.speed = is_medium ? t.medium_speed : t.large_speed;
        r.state = "not_sampled_fast_path"; r.loop_dt_us = t.dt_us; r.target_position = is_medium ? t.medium_target : t.large_target;
        r.goal_position = r.target_position; r.position_error = r.target_position - r.position; r.event = t.event;
        r.cpu_time_us = t.cpu_us; r.work_time_us = t.work_us; r.rate_hz = o.rate ? o.rate : 50;
        r.tick_start_us = t.time_us; r.trial_index = t.trial; r.cycle_index = t.cycle; log.row(r);
    };
    for (const auto& t : ticks) { emit(t, medium, true); emit(t, large, false); }
    log.flush();
}

int clamp_duty(int value, int limit) { return std::max(-limit, std::min(limit, value)); }
int v2_duty(double target, int position, int speed, int ff, const Options& o) {
    const double error = target - position;
    if (std::abs(error) <= o.settle_deadband) return 0;
    return clamp_duty(static_cast<int>(std::lround(o.controller_kp * error - o.controller_kd * speed)) + (error > 0 ? ff : -ff), o.controller_limit);
}

void collect_environment(const Options& options, const std::vector<MotorInfo>& motors) {
    mkdir_p(options.output);
    const std::string base = options.output.size() >= 4 && options.output.substr(options.output.size() - 4) == "/raw"
        ? options.output.substr(0, options.output.size() - 4) : options.output;
    mkdir_p(base);
    struct utsname uts {};
    if (::uname(&uts) != 0) throw std::runtime_error("uname failed");
    auto optional = [](const std::string& path) { try { return ev3bench::read_file(path); } catch (...) { return std::string(); } };
    const std::string os_release = optional("/etc/os-release");
    const std::string cpuinfo = optional("/proc/cpuinfo");
    const std::string meminfo = optional("/proc/meminfo");
    const int battery = ev3bench::read_battery_uv(options.power_supply);
    std::vector<std::pair<std::string, std::map<std::string, std::string>>> supplies;
    for (const auto& supply : directory_entries(options.power_supply)) {
        std::map<std::string, std::string> attributes;
        for (const auto& name : directory_entries(options.power_supply + "/" + supply)) {
            const std::string value = optional(options.power_supply + "/" + supply + "/" + name);
            if (!value.empty() && value.size() <= 4096) attributes[name] = value;
        }
        supplies.push_back({supply, attributes});
    }
#ifdef __GLIBC__
    const std::string libc = gnu_get_libc_version();
#else
    const std::string libc = "unknown";
#endif
    std::ostringstream json;
    json << "{\n  \"uname\": \"" << json_escape(std::string(uts.sysname) + " " + uts.release + " " + uts.version + " " + uts.machine) << "\",\n"
         << "  \"architecture\": \"" << json_escape(uts.machine) << "\",\n"
         << "  \"kernel\": \"" << json_escape(uts.release) << "\",\n"
         << "  \"libc\": \"" << json_escape(libc) << "\",\n"
         << "  \"os_release\": \"" << json_escape(os_release) << "\",\n"
         << "  \"battery_voltage\": " << std::fixed << std::setprecision(6) << battery / 1000000.0 << ",\n"
         << "  \"cpuinfo\": \"" << json_escape(cpuinfo) << "\",\n"
         << "  \"meminfo\": \"" << json_escape(meminfo) << "\",\n  \"power_supplies\": [\n";
    for (std::size_t i = 0; i < supplies.size(); ++i) {
        json << "    {\"name\": \"" << json_escape(supplies[i].first) << "\", \"attributes\": {";
        std::size_t index = 0;
        for (const auto& attribute : supplies[i].second) {
            if (index++) json << ", ";
            json << "\"" << json_escape(attribute.first) << "\": \"" << json_escape(attribute.second) << "\"";
        }
        json << "}}" << (i + 1 == supplies.size() ? "\n" : ",\n");
    }
    json << "  ],\n  \"motors\": [\n";
    for (std::size_t i = 0; i < motors.size(); ++i) {
        const auto& m = motors[i];
        auto attr = [&](const std::string& name) { return optional(m.path + "/" + name); };
        json << "    {\"path\": \"" << json_escape(m.path) << "\", \"address\": \"" << json_escape(m.address)
             << "\", \"driver_name\": \"" << json_escape(m.driver) << "\", \"count_per_rot\": " << m.count_per_rot
             << ", \"max_speed\": " << m.max_speed << ", \"commands\": \"" << json_escape(m.commands)
             << "\", \"stop_actions\": \"" << json_escape(m.stop_actions) << "\", \"polarity\": \"" << json_escape(attr("polarity"))
             << "\", \"position\": \"" << json_escape(attr("position")) << "\", \"speed\": \"" << json_escape(attr("speed"))
             << "\", \"duty_cycle\": \"" << json_escape(attr("duty_cycle")) << "\", \"duty_cycle_sp\": \"" << json_escape(attr("duty_cycle_sp"))
             << "\", \"state\": \"" << json_escape(attr("state")) << "\"}" << (i + 1 == motors.size() ? "\n" : ",\n");
    }
    json << "  ]\n}\n";
    std::ofstream jout(base + "/environment.json", std::ios::binary); jout << json.str();
    std::ofstream text(base + "/environment.txt", std::ios::binary);
    text << "uname: " << uts.sysname << ' ' << uts.release << ' ' << uts.version << ' ' << uts.machine << "\n"
         << "architecture: " << uts.machine << "\nkernel: " << uts.release << "\nlibc: " << libc
         << "\nbattery_voltage: " << battery / 1000000.0 << " V\n\n/etc/os-release:\n" << os_release
         << "\n\n/proc/cpuinfo:\n" << cpuinfo << "\n\n/proc/meminfo:\n" << meminfo << "\n\npower supplies:\n";
    for (const auto& supply : supplies) {
        text << supply.first << "\n";
        for (const auto& attribute : supply.second) text << "  " << attribute.first << "=" << attribute.second << "\n";
    }
    text << "\nmotors:\n";
    for (const auto& m : motors) text << m.path << " address=" << m.address << " driver=" << m.driver
        << " count_per_rot=" << m.count_per_rot << " max_speed=" << m.max_speed
        << " commands=[" << m.commands << "] stop_actions=[" << m.stop_actions << "]\n";
    std::cout << "wrote " << base << "/environment.{json,txt}\n";
}

void run_e0_manual(const Options& o, const std::vector<MotorInfo>& infos) {
    MotorSysfs large(ev3bench::find_motor(infos, o.large_address));
    MotorSysfs medium(ev3bench::find_motor(infos, o.medium_address));
    std::vector<MotorSysfs*> motors{&large, &medium};
    StopGuard guard(motors); preflight_stop(motors);
    std::cout << "Interactive E0: motors are stopped. Rotate only by hand, never while powered.\n";
    for (auto* motor : motors) {
        std::cout << "Set " << motor->info().address << " pointer to a recognizable angle, then press Enter." << std::endl;
        std::string input; std::getline(std::cin, input);
        CsvLog log(log_path(o, motor->info().address + "_manual_encoder"));
        const int start = motor->position();
        Row before = sample("E0", o.run_id, *motor, o, "manual-unpowered", 0, 0, start, "manual_start"); log.row(before);
        std::cout << "Turn the output shaft exactly one positive revolution, then press Enter." << std::endl;
        std::getline(std::cin, input);
        Row rotated = sample("E0", o.run_id, *motor, o, "manual-unpowered", 0, 0, start + motor->info().count_per_rot, "one_revolution"); log.row(rotated);
        motor->set_position(0);
        Row reset = sample("E0", o.run_id, *motor, o, "manual-unpowered", 0, 0, 0, "position_reset"); log.row(reset);
        std::cout << "Now turn the shaft slightly by hand and press Enter to verify position persists." << std::endl;
        std::getline(std::cin, input);
        Row persisted = sample("E0", o.run_id, *motor, o, "manual-unpowered", 0, 0, 0, "post_reset_manual_motion"); log.row(persisted);
    }
}

std::vector<MotorSysfs*> selected(const Options& o, MotorSysfs& large, MotorSysfs& medium) {
    if (o.motor == "large") return {&large};
    if (o.motor == "medium") return {&medium};
    if (o.motor == "all") return {&large, &medium};
    throw std::runtime_error("--motor must be large, medium, or all");
}

void run_e1(const Options& o, MotorSysfs& large, MotorSysfs& medium) {
    const std::vector<int> all_rates{25, 50, 75, 100};
    const std::vector<std::string> all_modes{"naive", "persistent", "timing-only"};
    const double duration = o.duration > 0 ? o.duration : 60.0;
    const auto active = selected(o, large, medium);
    for (const auto& mode : all_modes) {
        if (o.mode != "all" && o.mode != mode) continue;
        for (int rate : all_rates) {
            if (o.rate && o.rate != rate) continue;
            CsvLog log(log_path(o, mode + "_" + std::to_string(rate) + "hz_stationary"));
            std::vector<Row> deferred;
            cadence_loop(duration, rate, [&](std::int64_t dt) {
                std::vector<int> naive_positions, naive_speeds;
                if (mode == "naive") {
                    for (auto* motor : active) {
                        const auto& info = motor->info();
                        naive_positions.push_back(std::stoi(ev3bench::read_file(info.path + "/position")));
                        naive_speeds.push_back(std::stoi(ev3bench::read_file(info.path + "/speed")));
                        ev3bench::write_file(info.path + "/duty_cycle_sp", "0");
                    }
                } else if (mode == "timing-only") {
                    for (auto* motor : active) {
                        (void)motor->position(); (void)motor->speed(); motor->set_duty(0);
                    }
                } else { for (auto* motor : active) motor->set_duty(0); }
                if (mode == "timing-only") {
                    Row r; r.time_us = ev3bench::monotonic_us(); r.test_id = "E1"; r.run_id = o.run_id;
                    r.address = "both"; r.command_mode = mode; r.loop_dt_us = dt; r.cpu_time_us = process_cpu_us();
                    r.work_time_us = g_previous_work_us;
                    deferred.push_back(r);
                } else {
                    for (std::size_t index = 0; index < active.size(); ++index) {
                        const int pos = mode == "naive" ? naive_positions[index] : std::numeric_limits<int>::min();
                        const int speed = mode == "naive" ? naive_speeds[index] : std::numeric_limits<int>::min();
                        log.row(sample("E1", o.run_id, *active[index], o, mode, 0, dt, 0, {}, {}, pos, speed));
                    }
                }
            });
            for (const auto& row : deferred) log.row(row);
        }
    }
    if (o.arm && (o.rate == 0 || o.rate == 50) && (o.mode == "all" || o.mode == "persistent")) {
        CsvLog log(log_path(o, "persistent_50hz_free20"));
        for (auto* motor : active) { motor->set_duty(20); motor->command("run-direct"); }
        cadence_loop(duration, 50, [&](std::int64_t dt) {
            for (auto* motor : active) {
                motor->set_duty(20);
                log.row(sample("E1", o.run_id, *motor, o, "persistent", 20, dt));
            }
        });
        for (auto* motor : active) motor->stop();
    }
}

Row operation_row(const Options& o, const std::string& operation, const MotorInfo* motor,
                  int battery_uv, std::int64_t dt, std::int64_t duration_us, double rate, std::int64_t tick_start) {
    Row row;
    row.time_us = ev3bench::monotonic_us();
    row.test_id = "E1_5";
    row.run_id = o.run_id;
    row.address = motor ? motor->address : "bench";
    row.driver = motor ? motor->driver : "";
    row.battery_uv = battery_uv;
    row.command_mode = "persistent-decomposition";
    row.loop_dt_us = dt;
    row.cpu_time_us = process_cpu_us();
    row.rate_hz = rate;
    row.operation = operation;
    row.operation_duration_us = duration_us;
    row.tick_start_us = tick_start;
    return row;
}

void run_e1_5(const Options& o, MotorSysfs& large, MotorSysfs& medium) {
    const double rate = o.rate ? o.rate : 50.0;
    const double duration = o.duration > 0 ? o.duration : 60.0;
    CsvLog log(log_path(o, "persistent_" + rate_label(rate) + "hz_stationary_decomposition"), false);
    std::int64_t last_flush = ev3bench::monotonic_us();
    cadence_loop(duration, rate, [&](std::int64_t dt) {
        const std::int64_t tick_start = ev3bench::monotonic_us();
        int battery = 0;
        auto measure = [&](const std::string& name, const MotorInfo* info, const std::function<void()>& operation) {
            const std::int64_t start = ev3bench::monotonic_us();
            operation();
            const std::int64_t elapsed = ev3bench::monotonic_us() - start;
            log.row(operation_row(o, name, info, battery, dt, elapsed, rate, tick_start));
        };
        measure("medium_position_read", &medium.info(), [&] { (void)medium.position(); });
        measure("medium_speed_read", &medium.info(), [&] { (void)medium.speed(); });
        measure("medium_duty_read", &medium.info(), [&] { (void)medium.duty_cycle(); });
        measure("medium_state_read", &medium.info(), [&] { (void)medium.state(); });
        measure("large_position_read", &large.info(), [&] { (void)large.position(); });
        measure("large_speed_read", &large.info(), [&] { (void)large.speed(); });
        measure("large_duty_read", &large.info(), [&] { (void)large.duty_cycle(); });
        measure("large_state_read", &large.info(), [&] { (void)large.state(); });
        measure("battery_read", nullptr, [&] { battery = ev3bench::read_battery_uv(o.power_supply); });
        measure("medium_duty_write", &medium.info(), [&] { medium.set_duty(0); });
        measure("large_duty_write", &large.info(), [&] { large.set_duty(0); });
        const std::int64_t enqueue_start = ev3bench::monotonic_us();
        log.row(operation_row(o, "logger_enqueue_probe", nullptr, battery, dt, 0, rate, tick_start));
        const std::int64_t enqueue_elapsed = ev3bench::monotonic_us() - enqueue_start;
        log.row(operation_row(o, "logger_enqueue", nullptr, battery, dt, enqueue_elapsed, rate, tick_start));
        const std::int64_t now = ev3bench::monotonic_us();
        if (now - last_flush >= 1000000) {
            const std::int64_t flush_start = ev3bench::monotonic_us();
            log.flush();
            const std::int64_t flush_elapsed = ev3bench::monotonic_us() - flush_start;
            last_flush = ev3bench::monotonic_us();
            log.row(operation_row(o, "logger_flush_write", nullptr, battery, dt, flush_elapsed, rate, tick_start));
        }
        log.row(operation_row(o, "tick_total", nullptr, battery, dt, ev3bench::monotonic_us() - tick_start, rate, tick_start));
    });
}

struct MinimalSample {
    std::int64_t time_us = 0, dt_us = 0, work_us = 0, cpu_us = 0;
    int large_position = 0, large_speed = 0, medium_position = 0, medium_speed = 0;
};

void run_e1_minimal_once(const Options& o, MotorSysfs& large, MotorSysfs& medium, double rate, int repeat) {
    const double duration = o.duration > 0 ? o.duration : 120.0;
    const int battery_before = ev3bench::read_battery_uv(o.power_supply);
    std::vector<MinimalSample> samples;
    samples.reserve(static_cast<std::size_t>(duration * rate) + 16);
    cadence_loop(duration, rate, [&](std::int64_t dt) {
        const std::int64_t start = ev3bench::monotonic_us();
        MinimalSample record;
        record.time_us = start; record.dt_us = dt;
        record.large_position = large.position();
        record.large_speed = large.speed();
        record.medium_position = medium.position();
        record.medium_speed = medium.speed();
        large.set_duty(0); medium.set_duty(0);
        record.work_us = ev3bench::monotonic_us() - start;
        record.cpu_us = process_cpu_us();
        samples.push_back(record);
    });
    const int battery_after = ev3bench::read_battery_uv(o.power_supply);
    CsvLog log(log_path(o, "persistent_minimal_" + rate_label(rate) + "hz_repeat" + std::to_string(repeat)));
    for (const auto& record : samples) {
        for (const auto* motor : {&large, &medium}) {
            Row row;
            row.time_us = record.time_us; row.test_id = "E1_MINIMAL"; row.run_id = o.run_id;
            row.address = motor->info().address; row.driver = motor->info().driver;
            row.command_mode = "persistent-minimal"; row.loop_dt_us = record.dt_us;
            row.position = motor == &large ? record.large_position : record.medium_position;
            row.speed = motor == &large ? record.large_speed : record.medium_speed;
            row.duty_sp = 0; row.duty = 0; row.work_time_us = record.work_us;
            row.cpu_time_us = record.cpu_us; row.rate_hz = rate;
            row.battery_uv = (battery_before + battery_after) / 2;
            row.tick_start_us = record.time_us;
            log.row(row);
        }
    }
}

void run_e1_minimal(const Options& o, MotorSysfs& large, MotorSysfs& medium) {
    const std::vector<double> rates{25.0, 30.0, 33.333, 40.0, 50.0};
    for (double rate : rates) {
        if (o.rate && std::abs(rate - o.rate) > 0.01) continue;
        for (int repeat = 1; repeat <= 3; ++repeat) run_e1_minimal_once(o, large, medium, rate, repeat);
    }
}

void run_smoke(const Options& o, MotorSysfs& large, MotorSysfs& medium) {
    // Verify end-to-end logging before any motor motion test.
    // 10 seconds * 50 Hz * 2 motors is approximately 1000 motor rows.
    CsvLog log(log_path(o, "50hz_stationary"));
    cadence_loop(10.0, 50, [&](std::int64_t dt) {
        large.set_duty(0); medium.set_duty(0);
        log.row(sample("E_SMOKE", o.run_id, large, o, "smoke-stationary", 0, dt));
        log.row(sample("E_SMOKE", o.run_id, medium, o, "smoke-stationary", 0, dt));
    });
}

void run_e2(const Options& o, const std::vector<MotorSysfs*>& motors) {
    require_motion(o);
    const std::vector<int> duties{10, 15, 20, 25, 30, 40, 50, 60, 70, 80};
    const double sample_time = o.duration > 0 ? o.duration : 2.0;
    for (auto* motor : motors) for (int sign : {1, -1}) for (int magnitude : duties) {
        const int duty = sign * magnitude;
        CsvLog log(log_path(o, motor->info().address + "_duty" + std::to_string(duty)));
        motor->set_duty(duty); motor->command("run-direct"); sleep_seconds(0.5);
        cadence_loop(sample_time, 50, [&](std::int64_t dt) { log.row(sample("E2", o.run_id, *motor, o, "run-direct", duty, dt)); });
        motor->stop(); sleep_seconds(1.0);
    }
}

void run_e3(const Options& o, const std::vector<MotorSysfs*>& motors) {
    require_motion(o);
    const int rate = o.rate ? o.rate : 200;
    const double phase = o.duration > 0 ? o.duration : 2.0;
    for (auto* motor : motors) for (int duty : {30, 50, 70}) {
        CsvLog log(log_path(o, motor->info().address + "_step" + std::to_string(duty)));
        motor->set_duty(duty); motor->command("run-direct");
        cadence_loop(phase, rate, [&](std::int64_t dt) { log.row(sample("E3", o.run_id, *motor, o, "run-direct", duty, dt, 0, "acceleration")); });
        for (const std::string& action : {"coast", "brake", "hold"}) {
            if (motor->info().stop_actions.find(action) == std::string::npos) continue;
            motor->set_stop_action(action); motor->command("stop");
            cadence_loop(0.75, rate, [&](std::int64_t dt) { log.row(sample("E3", o.run_id, *motor, o, action, 0, dt, 0, "stop")); });
            if (action != "hold") { motor->set_duty(duty); motor->command("run-direct"); sleep_seconds(0.5); }
        }
        motor->stop(); sleep_seconds(1.0);
    }
}

void position_sequence(const Options& o, MotorSysfs& motor, const std::string& test,
                       int cycles, double kp, double kd, int duty_limit, double max_velocity,
                       double max_accel, const std::vector<double>& targets, double hold_seconds) {
    CsvLog log(log_path(o, motor.info().address + "_kp" + std::to_string(kp) + "_kd" + std::to_string(kd)));
    const int rate = o.rate ? o.rate : 50;
    const double dt = 1.0 / rate;
    double qref = motor.position(), velocity = 0;
    motor.set_duty(0); motor.command("run-direct");
    for (int cycle = 0; cycle < cycles && !g_stop.load(); ++cycle) for (std::size_t phase = 0; phase < targets.size(); ++phase) {
        const double target = targets[phase];
        const auto end = std::chrono::steady_clock::now() + std::chrono::microseconds(static_cast<long long>(hold_seconds * 1000000));
        while (!g_stop.load() && std::chrono::steady_clock::now() < end) {
            const double desired_v = std::max(-max_velocity, std::min(max_velocity, (target - qref) / dt));
            const double dv = std::max(-max_accel * dt, std::min(max_accel * dt, desired_v - velocity));
            velocity += dv; qref += velocity * dt;
            if ((target - qref) * velocity < 0) { qref = target; velocity = 0; }
            const int pos = motor.position(), speed = motor.speed();
            int duty = static_cast<int>(std::lround(kp * (qref - pos) + kd * (velocity - speed)));
            duty = std::max(-duty_limit, std::min(duty_limit, duty));
            motor.set_duty(duty);
            Row r = sample(test, o.run_id, motor, o, "run-direct-pd", duty, static_cast<std::int64_t>(dt * 1000000), qref,
                           qref == target ? "target_hold" : "trajectory");
            r.goal_position = target;
            r.target_speed = static_cast<int>(velocity); log.row(r);
            std::this_thread::sleep_for(std::chrono::microseconds(static_cast<int>(dt * 1000000)));
        }
    }
    motor.stop();
}

int static_ff_for(const Options& o, const MotorSysfs& motor) {
    return motor.info().driver == "lego-ev3-m-motor" ? o.medium_static_ff : o.large_static_ff;
}

void position_sequence_v2(const Options& o, MotorSysfs& motor, const std::string& test,
                          int cycles, double kp, double kd, int duty_limit, int static_ff,
                          const std::vector<double>& targets, double hold_seconds) {
    CsvLog log(log_path(o, motor.info().address + "_v2_kp" + std::to_string(kp) + "_kd" + std::to_string(kd) + "_ff" + std::to_string(static_ff)));
    const int rate = o.rate ? o.rate : 50;
    const double dt = 1.0 / rate, max_velocity = motor.info().max_speed * .35, max_accel = motor.info().max_speed;
    double qref = motor.position(), velocity = 0;
    motor.set_duty(0); motor.command("run-direct");
    for (int cycle = 0; cycle < cycles && !g_stop.load(); ++cycle) for (std::size_t phase = 0; phase < targets.size(); ++phase) {
        const double target = targets[phase];
        bool arrived = false;
        const auto end = std::chrono::steady_clock::now() + std::chrono::microseconds(static_cast<long long>(hold_seconds * 1000000));
        while (!g_stop.load() && std::chrono::steady_clock::now() < end) {
            const double desired_v = std::max(-max_velocity, std::min(max_velocity, (target - qref) / dt));
            velocity += std::max(-max_accel * dt, std::min(max_accel * dt, desired_v - velocity));
            qref += velocity * dt;
            if ((target - qref) * velocity < 0) { qref = target; velocity = 0; }
            const int pos = motor.position(), speed = motor.speed();
            const double error = qref - pos;
            int duty = 0;
            if (std::abs(error) > o.settle_deadband) {
                duty = static_cast<int>(std::lround(kp * error - kd * speed)) + (error > 0 ? static_ff : -static_ff);
                duty = std::max(-duty_limit, std::min(duty_limit, duty));
            }
            motor.set_duty(duty);
            const bool is_arrival = qref == target && std::abs(target - pos) <= o.settle_deadband && std::abs(speed) <= 5;
            Row r = sample(test, o.run_id, motor, o, "run-direct-pd-v2", duty, static_cast<std::int64_t>(dt * 1000000), qref,
                           is_arrival && !arrived ? "arrival" : (qref == target ? "target_hold" : "trajectory"));
            r.goal_position = target; r.target_speed = static_cast<int>(velocity); r.cycle_index = cycle;
            r.trial_index = cycle * static_cast<int>(targets.size()) + static_cast<int>(phase);
            log.row(r); arrived = arrived || is_arrival;
            std::this_thread::sleep_for(std::chrono::microseconds(static_cast<int>(dt * 1000000)));
        }
    }
    motor.stop();
}

void run_c2(const Options& o, const std::vector<MotorSysfs*>& motors) {
    require_motion(o);
    if (o.medium_static_ff <= 0 || o.large_static_ff <= 0) throw std::runtime_error("C2 requires positive static-friction seeds from C1");
    struct Gain { double kp, kd; int limit; };
    const std::vector<Gain> gains{{.20,.003,45},{.28,.004,55},{.35,.006,65}};
    for (auto* motor : motors) for (const auto& g : gains) {
        const double q = motor->info().count_per_rot / 4.0;
        position_sequence_v2(o, *motor, "C2", 20, g.kp, g.kd, g.limit, static_ff_for(o, *motor), {0,q,0,-q,0}, o.duration > 0 ? o.duration : .8);
    }
}

void run_c4(const Options& o, const std::vector<MotorSysfs*>& motors) {
    require_motion(o);
    if (o.medium_static_ff <= 0 || o.large_static_ff <= 0) throw std::runtime_error("C4 requires C1-derived static-friction seeds");
    for (auto* motor : motors) {
        const double q = motor->info().count_per_rot / 4.0;
        position_sequence_v2(o, *motor, "C4", 100, o.controller_kp, o.controller_kd, o.controller_limit,
                             static_ff_for(o, *motor), {q,-q}, o.duration > 0 ? o.duration : .8);
    }
}

void run_c3(const Options& o, const std::vector<MotorSysfs*>& motors) {
    require_motion(o);
    for (auto* motor : motors) {
        CsvLog log(log_path(o, motor->info().address + "_builtin_reference"));
        motor->set_speed_sp(static_cast<int>(motor->info().max_speed * .3));
        const int q = motor->info().count_per_rot / 4;
        const std::vector<int> targets{0,q,0,-q,0};
        for (int cycle = 0; cycle < 20 && !g_stop.load(); ++cycle) for (std::size_t phase = 0; phase < targets.size(); ++phase) {
            const int target = targets[phase];
            motor->set_position_sp(target); motor->command("run-to-abs-pos"); bool arrived = false;
            cadence_loop(o.duration > 0 ? o.duration : 1.0, 50, [&](std::int64_t dt) {
                Row r = sample("C3", o.run_id, *motor, o, "run-to-abs-pos", 0, dt, target);
                const bool here = std::abs(target - r.position) <= o.settle_deadband && std::abs(r.speed) <= 5;
                r.event = here && !arrived ? "arrival" : "builtin_sample"; r.goal_position = target; r.cycle_index = cycle;
                r.trial_index = cycle * static_cast<int>(targets.size()) + static_cast<int>(phase);
                arrived = arrived || here; log.row(r);
            });
        }
        motor->stop();
    }
}

void run_e4(const Options& o, const std::vector<MotorSysfs*>& motors) {
    require_motion(o);
    struct Gain { double kp, kd; int limit; };
    const std::vector<Gain> gains{{0.12, 0.0, 30}, {0.18, 0.002, 40}, {0.25, 0.004, 50}};
    for (auto* motor : motors) for (const auto& g : gains)
        {
        const double quarter = motor->info().count_per_rot / 4.0;
        position_sequence(o, *motor, "E4", 20, g.kp, g.kd, g.limit, motor->info().max_speed * 0.35,
                          motor->info().max_speed * 1.0, {0, quarter, 0, -quarter, 0}, o.duration > 0 ? o.duration : 0.7);
        }
}

void run_e5(const Options& o, const std::vector<MotorSysfs*>& motors) {
    require_motion(o);
    for (auto* motor : motors) {
        const double quarter = motor->info().count_per_rot / 4.0;
        position_sequence(o, *motor, "E5", 100, 0.18, 0.002, 40, motor->info().max_speed * 0.3,
                          motor->info().max_speed, {quarter, -quarter}, o.duration > 0 ? o.duration : 0.8);
    }
}

void run_e6(const Options& o, const std::vector<MotorSysfs*>& motors) {
    require_motion(o);
    const double phase = o.duration > 0 ? o.duration : 1.5;
    for (auto* motor : motors) for (int sign : {1, -1}) for (int magnitude = 5; magnitude <= 30; magnitude += 2) {
        const int duty = sign * magnitude;
        CsvLog log(log_path(o, motor->info().address + "_duty" + std::to_string(duty)));
        motor->set_duty(duty); motor->command("run-direct");
        cadence_loop(phase, 50, [&](std::int64_t dt) { log.row(sample("E6", o.run_id, *motor, o, "run-direct", duty, dt)); });
        motor->stop(); sleep_seconds(0.4);
    }
    for (auto* motor : motors) {
        const double quarter = motor->info().count_per_rot / 4.0;
        position_sequence(o, *motor, "E6", 5, 0.20, 0.003, 30,
                          motor->info().max_speed * 0.05, motor->info().max_speed * 0.2,
                          {0, quarter, 0, -quarter, 0}, o.duration > 0 ? o.duration : 1.0);
    }
}

struct StartTrial {
    MotorSysfs* motor;
    int duty;
    int index;
};

void deterministic_shuffle(std::vector<StartTrial>& trials) {
    std::uint32_t state = 0xC1A0BEEF;
    for (std::size_t i = trials.size(); i > 1; --i) {
        state = state * 1664525u + 1013904223u;
        std::swap(trials[i - 1], trials[state % i]);
    }
}

void run_c1(const Options& o, MotorSysfs& large, MotorSysfs& medium) {
    require_motion(o);
    std::vector<StartTrial> trials;
    const std::vector<int> medium_duties{15,17,19,20,21,22,23,24,25,27};
    const std::vector<int> large_duties{8,10,11,12,13,14,15,16,18,20,23};
    int index = 0;
    for (auto* motor : {&medium, &large}) {
        const auto& duties = motor == &medium ? medium_duties : large_duties;
        for (int sign : {1, -1}) for (int duty : duties) for (int repeat = 0; repeat < 10; ++repeat)
            trials.push_back({motor, sign * duty, index++});
    }
    deterministic_shuffle(trials);
    CsvLog log(log_path(o, "start_sustain_randomized"));
    for (const auto& trial : trials) {
        if (g_stop.load()) break;
        trial.motor->stop("brake"); sleep_seconds(.15);
        const std::int64_t command_time = ev3bench::monotonic_us();
        std::int64_t first_motion = 0;
        trial.motor->set_duty(trial.duty); trial.motor->command("run-direct");
        cadence_loop(.5, 200, [&](std::int64_t dt) {
            Row r = sample("C1", o.run_id, *trial.motor, o, "run-direct", trial.duty, dt, 0, "start_observation");
            r.trial_index = trial.index;
            if (!first_motion && std::abs(r.speed) >= 5) first_motion = r.time_us;
            log.row(r);
        });
        cadence_loop(1.0, 50, [&](std::int64_t dt) {
            Row r = sample("C1", o.run_id, *trial.motor, o, "run-direct", trial.duty, dt, 0, "stable_measurement");
            r.trial_index = trial.index; log.row(r);
        });
        Row result = sample("C1", o.run_id, *trial.motor, o, "run-direct", trial.duty, 0, 0, "trial_result");
        result.trial_index = trial.index;
        const std::int64_t latency = first_motion ? first_motion - command_time : std::numeric_limits<std::int64_t>::max();
        result.started_100ms = latency <= 100000; result.started_200ms = latency <= 200000;
        result.started_300ms = latency <= 300000; result.started_500ms = latency <= 500000;
        log.row(result);
        trial.motor->stop("brake"); sleep_seconds(.15);
    }
}

void run_e7(const Options& o, MotorSysfs& medium) {
    require_motion(o, "stall");
    const double contact_timeout = std::min(o.duration > 0 ? o.duration : 1.0, 1.0);
    for (int duty : {20, 25, 30}) {
        CsvLog log(log_path(o, medium.info().address + "_stall" + std::to_string(duty)));
        medium.set_duty(duty); medium.command("run-direct");
        cadence_loop(contact_timeout, 100, [&](std::int64_t dt) { log.row(sample("E7", o.run_id, medium, o, "run-direct", duty, dt, 0, "contact_window")); });
        medium.stop(); sleep_seconds(2.0);
    }
}

void run_e8(const Options& o, MotorSysfs& medium) {
    require_motion(o);
    const double pi = 3.14159265358979323846;
    for (double stroke : {0.5, 1.0, 2.0}) for (const std::string& waveform : {"triangle", "sine"}) {
        CsvLog log(log_path(o, waveform + "_stroke" + std::to_string(stroke)));
        const int rate = o.rate ? o.rate : 50, duty_limit = 50;
        const int center = medium.position(), amplitude = medium.info().count_per_rot / 4;
        const std::int64_t start = ev3bench::monotonic_us();
        medium.set_duty(0); medium.command("run-direct");
        cadence_loop(o.duration > 0 ? o.duration : stroke * 6, rate, [&](std::int64_t dt_us) {
            const double t = (ev3bench::monotonic_us() - start) / 1000000.0;
            // One half-period is one requested full-range stroke.
            const double phase = std::fmod(t / (2.0 * stroke), 1.0);
            const double wave = waveform == "sine" ? std::sin(2 * pi * phase) : 1.0 - 4.0 * std::abs(phase - 0.5);
            const double target = center + amplitude * wave;
            int duty = static_cast<int>(0.2 * (target - medium.position()) - 0.003 * medium.speed());
            duty = std::max(-duty_limit, std::min(duty_limit, duty)); medium.set_duty(duty);
            log.row(sample("E8", o.run_id, medium, o, "run-direct-pd-" + waveform, duty, dt_us, target));
        });
        medium.stop(); sleep_seconds(1.0);
    }
}

void run_c5(const Options& o, MotorSysfs& medium) {
    require_motion(o);
    if (o.medium_static_ff <= 0) throw std::runtime_error("C5 requires a C1-derived Medium static-friction seed");
    const double pi = 3.14159265358979323846;
    for (double stroke : {.5,1.0,2.0}) for (const std::string& waveform : {"triangle","sine"}) {
        CsvLog log(log_path(o, "v2_" + waveform + "_stroke" + std::to_string(stroke)));
        const int rate = o.rate ? o.rate : 50, limit = o.controller_limit;
        const int center = medium.position(), amplitude = medium.info().count_per_rot / 4;
        const std::int64_t start = ev3bench::monotonic_us();
        medium.set_duty(0); medium.command("run-direct");
        cadence_loop(o.duration > 0 ? o.duration : stroke * 6, rate, [&](std::int64_t dt_us) {
            const double t = (ev3bench::monotonic_us() - start) / 1000000.0;
            const double phase = std::fmod(t / (2.0 * stroke), 1.0);
            const double wave = waveform == "sine" ? std::sin(2 * pi * phase) : 1.0 - 4.0 * std::abs(phase - .5);
            const double target = center + amplitude * wave;
            const int pos = medium.position(), speed = medium.speed();
            const double error = target - pos;
            int duty = 0;
            if (std::abs(error) > o.settle_deadband) {
                duty = static_cast<int>(std::lround(o.controller_kp * error - o.controller_kd * speed)) + (error > 0 ? o.medium_static_ff : -o.medium_static_ff);
                duty = std::max(-limit, std::min(limit, duty));
            }
            medium.set_duty(duty);
            Row r = sample("C5", o.run_id, medium, o, "run-direct-pd-v2-" + waveform, duty, dt_us, target);
            r.goal_position = target; log.row(r);
        });
        medium.stop(); sleep_seconds(1.0);
    }
}

int fault_signal(const std::string& fault) {
    if (fault == "sigterm") return SIGTERM;
    if (fault == "sigkill") return SIGKILL;
    if (fault == "sigstop") return SIGSTOP;
    if (fault == "abort") return SIGABRT;
    throw std::runtime_error("invalid --fault");
}

void run_e9(const Options& o, MotorSysfs& motor) {
    require_motion(o, "crash");
    if (o.fault == "baseline") {
        CsvLog log(log_path(o, "baseline_no_safety"));
        const pid_t pid = ::fork();
        if (pid < 0) throw std::runtime_error("fork failed");
        if (pid == 0) { ::prctl(PR_SET_NAME, "bench-controller", 0, 0, 0); motor.set_duty(12); motor.command("run-direct"); ::_exit(99); }
        int status = 0; ::waitpid(pid, &status, 0);
        const auto fault_time = ev3bench::monotonic_us();
        log.row(sample("E9", o.run_id, motor, o, "run-direct", 12, 0, 0, "fault_injected", "baseline"));
        cadence_loop(0.15, 200, [&](std::int64_t dt) { log.row(sample("E9", o.run_id, motor, o, "run-direct", 12, dt, 0, "post_crash", "baseline")); });
        motor.stop();
        Row r = sample("E9", o.run_id, motor, o, "brake", 0, ev3bench::monotonic_us() - fault_time, 0, "external_watchdog_stop", "baseline"); log.row(r);
        return;
    }
    int heartbeat[2];
    if (::pipe(heartbeat) != 0) throw std::runtime_error("pipe failed");
    const pid_t pid = ::fork();
    if (pid < 0) throw std::runtime_error("fork failed");
    if (pid == 0) {
        ::prctl(PR_SET_NAME, "bench-controller", 0, 0, 0);
        ::close(heartbeat[0]);
        motor.set_duty(15); motor.command("run-direct");
        while (!g_stop.load()) {
            const std::int64_t now = ev3bench::monotonic_us();
            if (::write(heartbeat[1], &now, sizeof(now)) < 0) break;
            motor.set_duty(15);
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
        }
        motor.stop();
        ::_exit(0);
    }
    ::prctl(PR_SET_NAME, "bench-safety", 0, 0, 0);
    ::close(heartbeat[1]);
    std::this_thread::sleep_for(std::chrono::seconds(1));
    CsvLog log(log_path(o, o.fault));
    Row injection = sample("E9", o.run_id, motor, o, "run-direct", 15, 0, 0, "fault_injected", o.fault);
    const std::int64_t injected = ev3bench::monotonic_us();
    ::kill(pid, fault_signal(o.fault));
    injection.time_us = injected; log.row(injection);
    std::int64_t last_heartbeat = injected;
    int flags = ::fcntl(heartbeat[0], F_GETFL, 0); ::fcntl(heartbeat[0], F_SETFL, flags | O_NONBLOCK);
    while (ev3bench::monotonic_us() - last_heartbeat < o.heartbeat_ms * 1000LL && ev3bench::monotonic_us() - injected < 200000) {
        std::int64_t value = 0;
        while (::read(heartbeat[0], &value, sizeof(value)) == sizeof(value)) last_heartbeat = value;
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    // Revoke the normal writer before touching sysfs. SIGSTOP is already quiescent.
    ::kill(pid, SIGKILL);
    int status = 0; ::waitpid(pid, &status, 0);
    const std::int64_t detected = ev3bench::monotonic_us();
    motor.stop();
    const std::int64_t stop_written = ev3bench::monotonic_us();
    Row detection = sample("E9", o.run_id, motor, o, "safety-brake", 0, 0, 0, "supervisor_stop", o.fault);
    detection.heartbeat_age_us = detected - last_heartbeat;
    detection.detection_latency_us = detected - injected;
    detection.stop_command_latency_us = stop_written - detected;
    log.row(detection);
    cadence_loop(0.2, 200, [&](std::int64_t dt) { log.row(sample("E9", o.run_id, motor, o, "safety-brake", 0, dt, 0, "post_stop", o.fault)); });
    ::close(heartbeat[0]);
}

void run_c6(const Options& o, MotorSysfs& large) {
    require_motion(o, "crash");
    // Ten repetitions per injected fault plus an independent <=150 ms outer-watchdog baseline.
    std::vector<std::string> faults{"sigkill", "sigstop", "sigterm", "abort", "baseline"};
    if (o.mode != "all") {
        if (o.mode != "sigkill" && o.mode != "sigstop" && o.mode != "sigterm" && o.mode != "abort" && o.mode != "baseline")
            throw std::runtime_error("C6 --mode must be all|sigkill|sigstop|sigterm|abort|baseline");
        faults.assign(1, o.mode);
    }
    for (const std::string& fault : faults) {
        for (int trial = 0; trial < 10 && !g_stop.load(); ++trial) {
            Options one = o; one.fault = fault;
            run_e9(one, large);
            sleep_seconds(.2);
        }
    }
}

void run_e10(const Options& o, const std::vector<MotorSysfs*>& motors) {
    require_motion(o);
    for (auto* motor : motors) {
        CsvLog log(log_path(o, motor->info().address + "_stop"));
        motor->set_duty(15); motor->command("run-direct");
        g_stop.store(false);
        const double delay = o.duration > 0 ? o.duration : 2.0;
        cadence_loop(delay, 100, [&](std::int64_t dt) { log.row(sample("E10", o.run_id, *motor, o, "run-direct", 15, dt, 0, "pre_trigger")); });
        const std::int64_t trigger = ev3bench::monotonic_us(); motor->stop();
        const std::int64_t stop_written = ev3bench::monotonic_us();
        Row stop = sample("E10", o.run_id, *motor, o, "brake", 0, 0, 0, "stop_write", g_stop.load() ? "signal" : "timer");
        stop.stop_command_latency_us = stop_written - trigger; log.row(stop);
        g_stop.store(false);
        cadence_loop(0.5, 200, [&](std::int64_t dt) { log.row(sample("E10", o.run_id, *motor, o, "brake", 0, dt, 0, "deceleration")); });
    }
}

void run_c7(const Options& o, const std::vector<MotorSysfs*>& motors) {
    require_motion(o);
    for (auto* motor : motors) for (int duty : {30,50}) {
        CsvLog log(log_path(o, motor->info().address + "_moving_stop_" + std::to_string(duty)));
        motor->set_duty(duty); motor->command("run-direct");
        bool moving = false;
        cadence_loop(2.0, 200, [&](std::int64_t dt) {
            Row r = sample("C7", o.run_id, *motor, o, "run-direct", duty, dt, 0, "pre_trigger");
            moving = moving || std::abs(r.speed) >= 5; log.row(r);
        });
        // A low-duty point may be below static friction.  Record that fact but
        // continue with the higher-duty point and the other motor; it is not a
        // valid moving-stop measurement and must not abort the whole matrix.
        if (!moving) {
            motor->stop("brake");
            log.row(sample("C7", o.run_id, *motor, o, "brake", 0, 0, 0, "insufficient_motion"));
            continue;
        }
        const std::int64_t trigger = ev3bench::monotonic_us(); motor->stop("brake");
        const std::int64_t written = ev3bench::monotonic_us();
        Row stop = sample("C7", o.run_id, *motor, o, "brake", 0, 0, 0, "stop_write");
        stop.stop_command_latency_us = written - trigger; log.row(stop);
        cadence_loop(.75, 200, [&](std::int64_t dt) { log.row(sample("C7", o.run_id, *motor, o, "brake", 0, dt, 0, "deceleration")); });
    }
}

void run_d1(const Options& o, MotorSysfs& medium, MotorSysfs& large) {
    require_motion(o);
    const int repeats = 5;
    for (int duty : {30, 50, 70}) {
        int condition = 0;
        for (const std::pair<int, int>& pair : std::vector<std::pair<int, int>>{{duty,duty},{-duty,-duty},{duty,-duty},{-duty,duty},{duty,0},{0,duty}}) {
            const std::string batch = std::to_string(duty) + "_" + std::to_string(condition++);
            if (o.mode != "all" && o.mode != batch) continue;
            for (int repeat = 0; repeat < repeats; ++repeat) {
                const double duration = 6.0;
                auto ticks = active_dual_loop(o, medium, large, duration, [&](double t, int, int, int, int) {
                    const double scale = t < .5 ? t / .5 : (t > 3.5 ? std::max(0.0, (4.0 - t) / .5) : 1.0);
                    DualCommand c; c.medium_duty = static_cast<int>(std::lround(pair.first * scale)); c.large_duty = static_cast<int>(std::lround(pair.second * scale));
                    c.trial = repeat; c.event = t < .5 ? "ramp_up" : (t < 3.5 ? "steady" : (t < 4.0 ? "ramp_down" : "rest")); return c;
                }, true);
                write_dual_ticks(o, "m" + std::to_string(pair.first) + "_l" + std::to_string(pair.second) + "_r" + std::to_string(repeat), ticks, medium, large);
                sleep_seconds(.05);
            }
        }
    }
}

void run_d2(const Options& o, MotorSysfs& medium, MotorSysfs& large) {
    require_motion(o);
    for (int order = 0; order < 2; ++order) for (int repeat = 0; repeat < 10; ++repeat) {
        auto ticks = active_dual_loop(o, medium, large, 3.8, [&](double t, int, int, int, int) {
            int md = 0, ld = 0; const bool medium_first = order == 0;
            const double m_start = medium_first ? 0.0 : .5, l_start = medium_first ? .5 : 0.0;
            if (t >= m_start && t < 1.5) md = 40;
            if (t >= l_start && t < 2.5) ld = 40;
            if (t >= 2.0 && t < 3.5) md = -40;
            if (t >= 2.5 && t < 3.5) ld = -40;
            const char* event = "steady";
            if (std::abs(t-m_start)<.025) event = medium_first ? "medium_start" : "large_start";
            else if (std::abs(t-l_start)<.025) event = medium_first ? "large_start" : "medium_start";
            else if (std::abs(t-1.5)<.025) event = "medium_brake";
            else if (std::abs(t-2.0)<.025) event = "medium_reverse";
            else if (std::abs(t-2.5)<.025) event = "large_reverse";
            DualCommand c; c.medium_duty=md; c.large_duty=ld; c.trial=repeat; c.cycle=order; c.event=event; return c;
        }, true);
        write_dual_ticks(o, std::string(order ? "large_first" : "medium_first") + "_r" + std::to_string(repeat), ticks, medium, large);
    }
}

void run_d3(const Options& o, MotorSysfs& medium, MotorSysfs& large) {
    require_motion(o);
    for (int scenario = 0; scenario < 4; ++scenario) for (int repeat = 0; repeat < 20; ++repeat) {
        if (o.mode != "all" && o.mode != std::to_string(scenario)) continue;
        auto ticks = active_dual_loop(o, medium, large, 2.5, [&](double t, int, int, int, int) {
            const double ramp = t < .5 ? t/.5 : (t < 1.0 ? 1.0 : std::max(0.0, 1.0 - (t-1.0)/.5));
            int md = 40, ld = 40;
            if (t >= .5) {
                const double x = std::max(0.0, std::min(1.0, (t-.5)/.5));
                if (scenario == 0) { md = static_cast<int>(std::lround(40*(1-2*x))); ld=md; }
                if (scenario == 1) md = static_cast<int>(std::lround(40*(1-2*x)));
                if (scenario == 2) ld = static_cast<int>(std::lround(40*(1-2*x)));
                if (scenario == 3) { md = static_cast<int>(std::lround(40*(1-2*x))); ld = static_cast<int>(std::lround(-40*(1-2*x))); }
            } else { md=static_cast<int>(std::lround(md*ramp)); ld=static_cast<int>(std::lround(ld*ramp)); }
            DualCommand c; c.medium_duty=clamp_duty(md,50); c.large_duty=clamp_duty(ld,50); c.trial=repeat; c.cycle=scenario;
            c.event = t < .5 ? "ramp_positive" : (t < 1.0 ? "reversal_ramp" : "reversed_steady"); return c;
        }, true);
        write_dual_ticks(o, "scenario" + std::to_string(scenario) + "_r" + std::to_string(repeat), ticks, medium, large);
    }
}

struct TrajectoryCase { double ma, la, mf, lf, phase; const char* name; };

void run_d4(const Options& o, MotorSysfs& medium, MotorSysfs& large) {
    require_motion(o);
    const std::vector<TrajectoryCase> cases{{60,60,1,1,0,"same_phase"},{60,60,1,1,3.141592653589793,"opposite_phase"},{30,90,1,1,0,"amplitude"},{30,60,1,.5,0,"frequency"},{60,60,1,1,1.5707963267948966,"phase_shift"}};
    for (const auto& tc : cases) for (double period : {4.0,2.0,1.0}) {
        const int mc = medium.position(), lc = large.position();
        auto ticks = active_dual_loop(o, medium, large, 2*period, [&](double t, int mp, int ms, int lp, int ls) {
            DualCommand c; c.medium_target=mc+tc.ma*std::sin(2*3.141592653589793*t*tc.mf/period);
            c.large_target=lc+tc.la*std::sin(2*3.141592653589793*t*tc.lf/period+tc.phase);
            c.medium_duty=v2_duty(c.medium_target,mp,ms,o.medium_static_ff,o); c.large_duty=v2_duty(c.large_target,lp,ls,o.large_static_ff,o);
            c.event="tracking"; return c;
        });
        write_dual_ticks(o, std::string(tc.name)+"_period"+std::to_string(period), ticks, medium, large);
    }
}

double smoothstep5(double x) { x = std::max(0.0, std::min(1.0, x)); return x*x*x*(10 + x*(-15 + 6*x)); }

void run_d5(const Options& o, MotorSysfs& medium, MotorSysfs& large) {
    require_motion(o);
    const std::vector<std::pair<double,double>> targets{{90,90},{180,45},{45,180},{90,-90},{180,-90}};
    for (std::size_t pair = 0; pair < targets.size(); ++pair) for (int repeat = 0; repeat < 5; ++repeat) {
        if (o.mode != "all" && o.mode != std::to_string(pair)) continue;
        const int m0=medium.position(), l0=large.position(); const double mt=m0+targets[pair].first, lt=l0+targets[pair].second;
        const double duration = std::max(2.0, std::max(std::abs(targets[pair].first),std::abs(targets[pair].second))/60.0);
        auto ticks = active_dual_loop(o, medium, large, duration+.8, [&](double t,int mp,int ms,int lp,int ls) {
            const double s=smoothstep5(t/duration); DualCommand c; c.medium_target=m0+(mt-m0)*s; c.large_target=l0+(lt-l0)*s;
            c.medium_duty=v2_duty(c.medium_target,mp,ms,o.medium_static_ff,o); c.large_duty=v2_duty(c.large_target,lp,ls,o.large_static_ff,o);
            c.trial=repeat; c.cycle=static_cast<int>(pair); c.event=t<duration?"planned_tracking":"planned_hold"; return c;
        });
        write_dual_ticks(o,"pair"+std::to_string(pair)+"_r"+std::to_string(repeat),ticks,medium,large);
    }
}

void run_d6(const Options& o, MotorSysfs& medium, MotorSysfs& large) {
    require_motion(o);
    const std::vector<std::pair<double,double>> targets{{90,90},{180,45},{45,180},{90,-90},{180,-90}};
    for (std::size_t pair=0; pair<targets.size(); ++pair) for (int repeat=0; repeat<5; ++repeat) {
        if (o.mode != "all" && o.mode != std::to_string(pair)) continue;
        const int m0=medium.position(), l0=large.position(); const int mt=m0+static_cast<int>(targets[pair].first), lt=l0+static_cast<int>(targets[pair].second);
        const double duration=std::max(2.0,std::max(std::abs(targets[pair].first),std::abs(targets[pair].second))/60.0);
        BatterySampler battery(o); ActiveSafetySupervisor safety(medium,large); std::vector<FastTick> ticks; ticks.reserve(static_cast<std::size_t>((duration+.8)*50));
        medium.set_position_sp(mt); large.set_position_sp(lt); medium.set_speed_sp(180); large.set_speed_sp(180); medium.command("run-to-abs-pos"); large.command("run-to-abs-pos");
        auto next=std::chrono::steady_clock::now(), end=next+std::chrono::microseconds(static_cast<long long>((duration+.8)*1000000)); std::int64_t last=ev3bench::monotonic_us();
        while(!g_stop.load()&&!safety.tripped()&&std::chrono::steady_clock::now()<end) {
            const auto start=ev3bench::monotonic_us(); FastTick t; t.time_us=start; t.dt_us=start-last; t.cpu_us=process_cpu_us();
            t.medium_position=medium.position(); t.medium_speed=medium.speed(); t.large_position=large.position(); t.large_speed=large.speed(); t.medium_target=mt; t.large_target=lt; t.battery_uv=battery.voltage(); t.trial=repeat; t.cycle=pair; t.event="builtin_tracking";
            safety.heartbeat(); t.work_us=ev3bench::monotonic_us()-start; ticks.push_back(t); last=start; next+=std::chrono::microseconds(20000); std::this_thread::sleep_until(next);
        }
        medium.stop("brake"); large.stop("brake"); write_dual_ticks(o,"pair"+std::to_string(pair)+"_r"+std::to_string(repeat),ticks,medium,large);
    }
}

void run_d7(const Options& o, MotorSysfs& medium, MotorSysfs& large) {
    require_motion(o);
    const int m0=medium.position(), l0=large.position(); double mgoal=m0+120,lgoal=l0+60,mref=m0,lref=l0; unsigned rng=0x5EED1234U;
    auto ticks=active_dual_loop(o,medium,large,o.duration>0?o.duration:60.0,[&](double t,int mp,int ms,int lp,int ls) {
        const int slot=static_cast<int>(t/.3); bool changed = std::abs(t-slot*.3)<.025;
        if (changed) { rng=1664525U*rng+1013904223U; mgoal=m0+(static_cast<int>((rng>>16)%241)-120); rng=1664525U*rng+1013904223U; lgoal=l0+(static_cast<int>((rng>>16)%201)-100); }
        const double step=2.4; mref += std::max(-step,std::min(step,mgoal-mref)); lref += std::max(-step,std::min(step,lgoal-lref));
        DualCommand c; c.medium_target=mref;c.large_target=lref;c.medium_duty=v2_duty(mref,mp,ms,o.medium_static_ff,o);c.large_duty=v2_duty(lref,lp,ls,o.large_static_ff,o);c.cycle=slot;c.event=changed?"target_replaced":"latest_target_tracking";return c;
    });
    write_dual_ticks(o,"latest_target_wins",ticks,medium,large);
}

void run_d8(const Options& o, MotorSysfs& medium, MotorSysfs& large) {
    require_motion(o);
    for(int repeat=0;repeat<3;++repeat) { const int mc=medium.position(),lc=large.position();
        if (o.mode != "all" && o.mode != std::to_string(repeat+1)) continue;
        auto ticks=active_dual_loop(o,medium,large,o.duration>0?o.duration:120.0,[&](double t,int mp,int ms,int lp,int ls){
            DualCommand c;c.medium_target=mc+45*std::sin(2*3.141592653589793*t/4.0);c.large_target=lc+45*std::sin(2*3.141592653589793*t/4.0+1.5707963267948966);
            c.medium_duty=v2_duty(c.medium_target,mp,ms,o.medium_static_ff,o);c.large_duty=v2_duty(c.large_target,lp,ls,o.large_static_ff,o);c.trial=repeat;c.event="active_tracking";return c;});
        write_dual_ticks(o,"active_50hz_repeat"+std::to_string(repeat+1),ticks,medium,large);
    }
}

void run_e12(const Options& o, MotorSysfs& large, MotorSysfs& medium) {
    if (o.spin_only) require_motion(o);
    const int rate = o.rate ? o.rate : 50;
    const double stationary = o.duration > 0 ? o.duration : 120.0;
    CsvLog log(log_path(o, "two_motor_" + std::to_string(rate) + "hz"));
    if (!o.spin_only) {
        cadence_loop(stationary, rate, [&](std::int64_t dt) {
            large.set_duty(0); medium.set_duty(0);
            log.row(sample("E12", o.run_id, large, o, "persistent", 0, dt));
            log.row(sample("E12", o.run_id, medium, o, "persistent", 0, dt));
        });
    }
    if (!o.arm) return;
    large.set_duty(20); medium.set_duty(20); large.command("run-direct"); medium.command("run-direct");
    cadence_loop(o.duration > 0 ? o.duration : 30.0, rate, [&](std::int64_t dt) {
        large.set_duty(20); medium.set_duty(20);
        log.row(sample("E12", o.run_id, large, o, "persistent-free", 20, dt));
        log.row(sample("E12", o.run_id, medium, o, "persistent-free", 20, dt));
    });
    large.stop(); medium.stop();
}

void run_e13(const Options& o, const std::vector<MotorSysfs*>& motors) {
    require_motion(o);
    for (auto* motor : motors) {
        CsvLog log(log_path(o, motor->info().address + "_builtin"));
        motor->set_speed_sp(static_cast<int>(motor->info().max_speed * 0.3));
        const int quarter = motor->info().count_per_rot / 4;
        for (int cycle = 0; cycle < 20 && !g_stop.load(); ++cycle) for (int target : {0, quarter, 0, -quarter, 0}) {
            motor->set_position_sp(target); motor->command("run-to-abs-pos");
            cadence_loop(o.duration > 0 ? o.duration : 1.0, 50, [&](std::int64_t dt) {
                log.row(sample("E13", o.run_id, *motor, o, "run-to-abs-pos", 0, dt, target));
            });
        }
        motor->stop();
    }
}

}  // namespace

int main(int argc, char** argv) {
    try {
        std::signal(SIGINT, signal_handler);
        std::signal(SIGTERM, signal_handler);
        std::signal(SIGHUP, signal_handler);
        std::signal(SIGALRM, signal_handler);
        ::alarm(3600);
        const Options options = parse_args(argc, argv);
        mkdir_p(options.output);
        const auto infos = ev3bench::discover_motors(options.motor_class);
        if (options.test == "e0") {
            collect_environment(options, infos);
            if (options.manual_e0) run_e0_manual(options, infos);
            return 0;
        }
        if (options.test == "e11") {
            std::cout << "E11 is computed offline by tools/ev3_validation/analyze.py from voltage-tagged runs.\n"; return 0;
        }
        const MotorInfo large_info = ev3bench::find_motor(infos, options.large_address);
        const MotorInfo medium_info = ev3bench::find_motor(infos, options.medium_address);
        if (large_info.driver != "lego-ev3-l-motor") {
            throw std::runtime_error("configured Large address " + large_info.address + " has driver " + large_info.driver + "; expected lego-ev3-l-motor");
        }
        if (medium_info.driver != "lego-ev3-m-motor") {
            throw std::runtime_error("configured Medium address " + medium_info.address + " has driver " + medium_info.driver + "; expected lego-ev3-m-motor");
        }
        MotorSysfs large(large_info);
        MotorSysfs medium(medium_info);
        std::vector<MotorSysfs*> all{&large, &medium};
        StopGuard guard(all);
        preflight_stop(all);
        const auto motors = selected(options, large, medium);
        if (options.test == "smoke") run_smoke(options, large, medium);
        else if (options.test == "e1") run_e1(options, large, medium);
        else if (options.test == "e1_5") run_e1_5(options, large, medium);
        else if (options.test == "e1_minimal") run_e1_minimal(options, large, medium);
        else if (options.test == "e2") run_e2(options, motors);
        else if (options.test == "e3") run_e3(options, motors);
        else if (options.test == "e4") run_e4(options, motors);
        else if (options.test == "e5") run_e5(options, motors);
        else if (options.test == "e6") run_e6(options, motors);
        else if (options.test == "c1") run_c1(options, large, medium);
        else if (options.test == "c2") run_c2(options, motors);
        else if (options.test == "c3") run_c3(options, motors);
        else if (options.test == "c4") run_c4(options, motors);
        else if (options.test == "c5") run_c5(options, medium);
        else if (options.test == "c6") run_c6(options, large);
        else if (options.test == "c7") run_c7(options, motors);
        else if (options.test == "d1") run_d1(options, medium, large);
        else if (options.test == "d2") run_d2(options, medium, large);
        else if (options.test == "d3") run_d3(options, medium, large);
        else if (options.test == "d4") run_d4(options, medium, large);
        else if (options.test == "d5") run_d5(options, medium, large);
        else if (options.test == "d6") run_d6(options, medium, large);
        else if (options.test == "d7") run_d7(options, medium, large);
        else if (options.test == "d8") run_d8(options, medium, large);
        else if (options.test == "e7") run_e7(options, medium);
        else if (options.test == "e8") run_e8(options, medium);
        else if (options.test == "e9") run_e9(options, options.motor == "medium" ? medium : large);
        else if (options.test == "e10") run_e10(options, motors);
        else if (options.test == "e12") run_e12(options, large, medium);
        else if (options.test == "e13") run_e13(options, motors);
        else throw std::runtime_error("unknown test: " + options.test + "\n" + usage());
        guard.stop();
        std::cout << "completed " << options.test << "; logs: " << options.output << "\n";
        return g_stop.load() ? 130 : 0;
    } catch (const std::exception& error) {
        std::cerr << "ev3-bench: " << error.what() << '\n';
        return 1;
    }
}
