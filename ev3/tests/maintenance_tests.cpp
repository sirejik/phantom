#include <sys/stat.h>
#include <unistd.h>

#include <chrono>
#include <fstream>
#include <iostream>
#include <stdexcept>

#include "phantom/maintenance.hpp"

using namespace phantom;
namespace {
void require(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}
template <class Function>
void rejects(Function function) {
  bool rejected = false;
  try {
    function();
  } catch (const std::exception&) {
    rejected = true;
  }
  require(rejected, "invalid input was accepted");
}
struct TemporaryDirectory {
  char path[64] = "/tmp/phantom-maintenance-tests-XXXXXX";
  TemporaryDirectory() { require(mkdtemp(path) != nullptr, "mkdtemp failed"); }
  ~TemporaryDirectory() {
    unlink((std::string(path) + "/report.json").c_str());
    unlink((std::string(path) + "/link").c_str());
    rmdir(path);
  }
};
}  // namespace
int main() {
  try {
    for (const auto& path :
         {"../file", "/file", "a//b", "a/../b", "a\\b", "a\nb", "."})
      require(!maintenance_safe_relative(path), "unsafe archive path accepted");
    require(maintenance_safe_relative("bin/phantom-controller"),
            "valid archive path rejected");
    require(maintenance_motor_stationary("0", "0", "0", "", "brake"),
            "stationary motor rejected");
    require(!maintenance_motor_stationary("0", "0", "1", "", "brake"),
            "moving motor accepted");
    require(!maintenance_motor_stationary("0", "1", "0", "", "brake"),
            "powered motor accepted");
    require(!maintenance_motor_stationary("0", "0", "0", "running", "brake"),
            "running motor accepted");
    require(!maintenance_motor_stationary("0", "0", "0", "", "coast"),
            "coast motor accepted");
    require(maintenance_clock_trust(1788706800, false) ==
                "HOST_CORRELATION_REQUIRED",
            "clock trust incorrect");
    rejects([] { maintenance_clock_trust(42, false); });
    const auto command =
        maintenance_command({"printf", "%s", "a b; $(ignored)"});
    require(command.code == 0 && command.output == "a b; $(ignored)",
            "command used shell interpolation");
    require(maintenance_command({"sh", "-c", "exit 7"}).code == 7,
            "exit status lost");
    const auto started = std::chrono::steady_clock::now();
    rejects([] { maintenance_command({"sh", "-c", "sleep 10 & wait"}, 1); });
    require(
        std::chrono::steady_clock::now() - started < std::chrono::seconds(4),
        "timeout not bounded");
    TemporaryDirectory temporary;
    const auto file = std::string(temporary.path) + "/report.json";
    maintenance_write(file, "{\"value\":1e+30}");
    require(maintenance_digest(file, true) != maintenance_digest(file),
            "bundle LF trimming lost");
    maintenance_write(file, "{\"status\":\"PASS\",\"scope\":0}");
    auto json = maintenance_json(file);
    require(maintenance_string(json, "status") == "PASS",
            "report round trip failed");
    rejects([&] { maintenance_string(json, "missing"); });
    maintenance_write(file, "{\"status\":\"PASS\",\"status\":\"FAIL\"}");
    rejects([&] { maintenance_json(file); });
    maintenance_write(file, "[]");
    rejects([&] { maintenance_json(file); });
    const auto escaped = maintenance_quote("a\n\"\\");
    require(escaped == "\"a\\u000a\\\"\\\\\"", "invalid JSON escaping");
    require(symlink("report.json",
                    (std::string(temporary.path) + "/link").c_str()) == 0,
            "symlink failed");
    rejects([&] { maintenance_files(temporary.path); });
    rejects([&] { maintenance_validate_bundle(temporary.path); });
    std::cout << "maintenance regression tests PASS\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
