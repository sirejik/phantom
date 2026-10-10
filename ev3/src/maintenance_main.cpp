#include <algorithm>
#include <chrono>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>

#include "phantom/maintenance.hpp"
#include "phantom/network_wire.hpp"
using namespace phantom;
static std::string steps(const std::string& path, bool start) {
  std::istringstream lines(read_bounded_file(path));
  std::string line, out = "[";
  while (std::getline(lines, line)) {
    std::istringstream row(line);
    std::vector<std::string> fields;
    std::string field;
    while (std::getline(row, field, '\t')) fields.push_back(field);
    if (fields.size() != (start ? 6u : 3u))
      throw std::runtime_error("invalid report step");
    if (out.size() > 1) out += ",";
    out += "{";
    const std::vector<std::string> names =
        start ? std::vector<std::string>{"unit",
                                         "status",
                                         "result",
                                         "exec_main_code",
                                         "exec_main_status",
                                         "duration_ms"}
              : std::vector<std::string>{"step", "status", "duration_ms"};
    for (std::size_t i = 0; i < names.size(); ++i) {
      if (i) out += ",";
      out += maintenance_quote(names[i]) + ":" +
             (i + 1 == names.size() ? std::to_string(std::stoull(fields[i]))
                                    : maintenance_quote(fields[i]));
    }
    out += "}";
  }
  return out + "]";
}
int main(int argc, char** argv) {
  try {
    if (argc < 2) throw std::runtime_error("maintenance operation required");
    std::string mode = argv[1];
    auto arg = [&](int n) -> std::string {
      if (n >= argc) throw std::runtime_error("missing maintenance argument");
      return argv[n];
    };
    if (mode == "time") {
      std::cout << std::chrono::duration_cast<std::chrono::milliseconds>(
                       std::chrono::steady_clock::now().time_since_epoch())
                       .count()
                << '\n';
      return 0;
    }
    if (mode == "get") {
      auto value = maintenance_json(arg(2));
      std::cout << maintenance_string(value, arg(3)) << '\n';
      return 0;
    }
    if (mode == "manifest") {
      auto v = maintenance_json(arg(2));
      std::uint64_t schema = 0;
      if (!json_uint(v, "schema_version", 5, 5, schema) ||
          maintenance_string(v, "component") != "EV3" ||
          maintenance_string(v, "build_identity_schema") !=
              "PHANTOM-BUILD-V4" ||
          maintenance_string(v, "build_id") != arg(3))
        throw std::runtime_error("manifest mismatch");
      std::cout << arg(3) << '\n';
      return 0;
    }
    if (mode == "validate-bundle") {
      maintenance_validate_bundle(arg(2));
      return 0;
    }
    if (mode == "archive-check") {
      const auto result = maintenance_command({"tar", "-tvzf", arg(2)}, 30);
      if (result.code) throw std::runtime_error("archive cannot be read");
      std::istringstream lines(result.output);
      std::set<std::string> names;
      std::string line;
      while (std::getline(lines, line)) {
        std::istringstream row(line);
        std::string permissions, owner, size, date, time, name;
        row >> permissions >> owner >> size >> date >> time >> name;
        if (!name.empty() && name.back() == '/') name.pop_back();
        std::string extra;
        row >> extra;
        if (!extra.empty() || permissions.empty() ||
            (permissions[0] != 'd' && permissions[0] != '-') ||
            !maintenance_safe_relative(name) || !names.insert(name).second)
          throw std::runtime_error("unsafe archive inventory");
      }
      for (const auto& file :
           {"build-manifest.json", "SHA256SUMS", "bin/phantom-controller",
            "bin/phantom-safety", "bin/phantom-network", "bin/phantom-mdns",
            "bin/phantom-maintenance", "bin/phantom-device-integration-test"})
        if (!names.count(file)) throw std::runtime_error("incomplete archive");
      return 0;
    }
    if (mode == "checksum-inventory") {
      auto actual = maintenance_files(arg(2));
      actual.erase(std::remove(actual.begin(), actual.end(), "SHA256SUMS"),
                   actual.end());
      std::set<std::string> listed;
      std::istringstream input(read_bounded_file(arg(2) + "/SHA256SUMS"));
      std::string line;
      while (std::getline(input, line)) {
        if (line.size() < 67 || line.substr(64, 2) != "  ")
          throw std::runtime_error("invalid checksum entry");
        std::string name = line.substr(66);
        unsigned char hash[32];
        if (!parse_hex(line.substr(0, 64), hash, 32) ||
            !maintenance_safe_relative(name) || !listed.insert(name).second)
          throw std::runtime_error("invalid checksum inventory");
      }
      if (listed != std::set<std::string>(actual.begin(), actual.end()))
        throw std::runtime_error("checksum inventory mismatch");
      return 0;
    }
    if (mode == "install-report" || mode == "start-report") {
      const bool start = mode == "start-report";
      std::string out =
          "{\"schema_version\":1,\"component\":\"EV3\",\"phase\":" +
          maintenance_quote(start ? "START" : "INSTALL") +
          ",\"status\":" + maintenance_quote(arg(3));
      auto field = [&](const std::string& name, int position) {
        out += "," + maintenance_quote(name) + ":" +
               maintenance_quote(arg(position));
      };
      if (start) {
        field("started_at", 4);
        field("finished_at", 5);
        field("build_id", 8);
        field("profile", 9);
        field("first_failed_service", 10);
        out +=
            ",\"first_failure_at_ms\":" +
            (arg(11).empty() ? "null" : std::to_string(std::stoull(arg(11))));
        field("failure_detail", 12);
        field("terminal_state", 13);
        field("diagnostics_directory", 14);
        out += ",\"steps\":" + steps(arg(15), true);
      } else {
        field("detail", 4);
        field("started_at", 5);
        field("finished_at", 6);
        field("release_id", 9);
        field("build_id", 10);
        field("profile", 11);
        field("artifact_sha256", 12);
        field("previous_release", 13);
        field("installed_path", 14);
        field("terminal_state", 15);
        out += ",\"steps\":" + steps(arg(16), false);
      }
      out +=
          ",\"duration_ms\":" +
          std::to_string(
              std::max<long long>(0, std::stoll(arg(start ? 7 : 8)) -
                                         std::stoll(arg(start ? 6 : 7)))) +
          ",\"reason\":" +
          maintenance_quote(arg(3) == "PASS" ? (start ? "STARTED" : "INSTALLED")
                                             : (start ? "SERVICE_START_FAILED"
                                                      : "INSTALL_FAILED")) +
          ",\"hardware_evidence_state\":\"NOT_QUALIFICATION_EVIDENCE\"}";
      maintenance_write(arg(2), out);
      return 0;
    }
    if (mode == "integration-test") return maintenance_integration(arg(2));
    if (mode == "integration-failure-report") {
      const auto path = "/var/lib/phantom/device-integration-test.json";
      JsonValue payload;
      try {
        payload = maintenance_json(path);
      } catch (...) {
        payload.kind = JsonValue::Kind::Object;
      }
      auto field = [&](const std::string& name, const std::string& value) {
        JsonValue v;
        v.kind = JsonValue::Kind::String;
        v.text = value;
        payload.members[name] = v;
      };
      field("status", "FAIL");
      field("reason", "DEVICE_CHECK_FAILED");
      field("build_id", arg(2));
      field("component", "EV3");
      field("terminal_state", arg(3));
      field("phase", "DEVICE INTEGRATION TEST");
      field("hardware_evidence_state", "DEVICE");
      JsonValue schema;
      schema.kind = JsonValue::Kind::Number;
      schema.number = 2;
      payload.members["schema_version"] = schema;
      maintenance_write(path, maintenance_serialize(payload));
      return 0;
    }
    throw std::runtime_error("unknown maintenance operation");
  } catch (const std::exception& e) {
    std::cerr << "maintenance: " << e.what() << '\n';
    return 1;
  }
}
