#include <dirent.h>
#include <fcntl.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <thread>

#include "phantom/maintenance.hpp"
#include "phantom/network_wire.hpp"
namespace phantom {
CommandResult maintenance_command(const std::vector<std::string>& args,
                                  unsigned timeout) {
  if (args.empty()) throw std::runtime_error("empty maintenance command");
  int pipes[2];
  if (pipe(pipes)) throw std::runtime_error("pipe failed");
  const auto pid = fork();
  if (pid < 0) {
    close(pipes[0]);
    close(pipes[1]);
    throw std::runtime_error("fork failed");
  }
  if (pid == 0) {
    setpgid(0, 0);
    close(pipes[0]);
    dup2(pipes[1], 1);
    dup2(pipes[1], 2);
    close(pipes[1]);
    std::vector<char*> argv;
    for (const auto& arg : args) argv.push_back(const_cast<char*>(arg.c_str()));
    argv.push_back(nullptr);
    execvp(argv[0], argv.data());
    _exit(127);
  }
  close(pipes[1]);
  fcntl(pipes[0], F_SETFL, O_NONBLOCK);
  std::string output;
  int status = 0;
  bool done = false, eof = false;
  const auto deadline =
      std::chrono::steady_clock::now() + std::chrono::seconds(timeout);
  while (!done || !eof) {
    char buffer[4096];
    const auto count = read(pipes[0], buffer, sizeof(buffer));
    if (count > 0) {
      output.append(buffer, static_cast<std::size_t>(count));
      if (output.size() > 4 * 1024 * 1024) {
        kill(-pid, SIGKILL);
        waitpid(pid, &status, 0);
        close(pipes[0]);
        throw std::runtime_error("maintenance output exceeded bound");
      }
    } else if (count == 0)
      eof = true;
    if (!done) done = waitpid(pid, &status, WNOHANG) == pid;
    if (std::chrono::steady_clock::now() >= deadline && (!done || !eof)) {
      kill(-pid, SIGKILL);
      if (!done) waitpid(pid, &status, 0);
      close(pipes[0]);
      throw std::runtime_error("maintenance command timeout");
    }
    if (!done || !eof)
      std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }
  close(pipes[0]);
  return {WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status),
          output};
}
JsonValue maintenance_json(const std::string& path) {
  auto raw = read_bounded_file(path, 4 * 1024 * 1024);
  if (raw.compare(0, 3, "\xef\xbb\xbf") == 0) raw.erase(0, 3);
  JsonValue value;
  std::string error;
  if (!parse_json(raw, value, error, 4 * 1024 * 1024) || !value.is_object())
    throw std::runtime_error("invalid maintenance JSON");
  return value;
}
std::string maintenance_string(const JsonValue& value,
                               const std::string& field) {
  std::string result;
  if (!json_string(value, field, result))
    throw std::runtime_error("missing string field: " + field);
  return result;
}
std::string maintenance_quote(const std::string& value) {
  std::ostringstream out;
  out << '"';
  for (unsigned char c : value) {
    if (c == '"' || c == '\\')
      out << '\\' << c;
    else if (c < 32)
      out << "\\u" << std::hex << std::setw(4) << std::setfill('0')
          << static_cast<unsigned>(c) << std::dec;
    else
      out << c;
  }
  out << '"';
  return out.str();
}
std::string maintenance_serialize(const JsonValue& v) {
  switch (v.kind) {
    case JsonValue::Kind::Null:
      return "null";
    case JsonValue::Kind::Bool:
      return v.boolean ? "true" : "false";
    case JsonValue::Kind::String:
      return maintenance_quote(v.text);
    case JsonValue::Kind::Number: {
      std::ostringstream out;
      out << std::setprecision(17) << v.number;
      return out.str();
    }
    case JsonValue::Kind::Array: {
      std::string out = "[";
      for (const auto& x : v.items) {
        if (out.size() > 1) out += ",";
        out += maintenance_serialize(x);
      }
      return out + "]";
    }
    case JsonValue::Kind::Object: {
      std::string out = "{";
      for (const auto& x : v.members) {
        if (out.size() > 1) out += ",";
        out +=
            maintenance_quote(x.first) + ":" + maintenance_serialize(x.second);
      }
      return out + "}";
    }
  }
  throw std::runtime_error("unknown JSON kind");
}
bool maintenance_safe_relative(const std::string& path) {
  if (path.empty() || path[0] == '/' || path.find('\\') != std::string::npos ||
      std::any_of(path.begin(), path.end(),
                  [](unsigned char c) { return c <= 32; }))
    return false;
  std::istringstream parts(path);
  std::string part;
  while (std::getline(parts, part, '/'))
    if (part.empty() || part == "." || part == "..") return false;
  return true;
}
bool maintenance_motor_stationary(const std::string& duty_sp,
                                  const std::string& duty,
                                  const std::string& speed,
                                  const std::string& state,
                                  const std::string& stop_action) {
  return duty_sp == "0" && duty == "0" && speed == "0" &&
         stop_action == "brake" && state.find("running") == std::string::npos &&
         state.find("ramping") == std::string::npos;
}
std::string maintenance_clock_trust(std::uint64_t epoch_seconds,
                                    bool synchronized) {
  if (epoch_seconds < 1577836800)
    throw std::runtime_error("wall clock is uninitialised");
  return synchronized ? "SYNCHRONIZED" : "HOST_CORRELATION_REQUIRED";
}
std::string maintenance_digest(const std::string& path, bool trim) {
  auto bytes = read_bounded_file(path, 64 * 1024 * 1024);
  if (trim && !bytes.empty() && bytes.back() == '\n') bytes.pop_back();
  NetworkCrypto crypto;
  auto hash = crypto.hash(reinterpret_cast<const unsigned char*>(bytes.data()),
                          bytes.size());
  return hex(hash.data(), hash.size());
}
void maintenance_validate_bundle(const std::string& root) {
  auto manifest = maintenance_json(root + "/build-manifest.json"),
       config = maintenance_json(root + "/config.generated.json"),
       bundle = maintenance_json(root + "/commissioning-bundle.generated.json");
  if (maintenance_string(manifest, "component") != "EV3" ||
      maintenance_string(manifest, "build_identity_schema") !=
          "PHANTOM-BUILD-V4")
    throw std::runtime_error("invalid EV3 manifest");
  std::uint64_t schema = 0;
  if (!json_uint(manifest, "schema_version", 5, 5, schema))
    throw std::runtime_error("invalid manifest schema");
  if (maintenance_digest(root + "/config.generated.json") !=
          maintenance_string(manifest, "config_hash") ||
      maintenance_digest(root + "/commissioning-bundle.generated.json", true) !=
          maintenance_string(manifest, "commissioning_bundle_hash"))
    throw std::runtime_error("config/bundle hash mismatch");
  if (maintenance_string(config, "build_profile") !=
      maintenance_string(manifest, "build_profile"))
    throw std::runtime_error("profile mismatch");
  for (const auto& field : {"qualification_only", "actuator_scope_mask",
                            "safety_observation_mask"}) {
    auto a = config.find(field), b = bundle.find(field);
    if (!a || !b || maintenance_serialize(*a) != maintenance_serialize(*b))
      throw std::runtime_error("config/bundle scope mismatch");
  }
}
void maintenance_write(const std::string& path, const std::string& content) {
  const auto temp = path + ".tmp";
  std::ofstream out(temp, std::ios::binary | std::ios::trunc);
  out << content << '\n';
  out.close();
  if (!out || rename(temp.c_str(), path.c_str()))
    throw std::runtime_error("cannot write maintenance report");
}
static void collect(const std::string& root, const std::string& relative,
                    std::vector<std::string>& files) {
  auto directory = opendir((root + "/" + relative).c_str());
  if (!directory) throw std::runtime_error("cannot enumerate inventory");
  try {
    while (auto entry = readdir(directory)) {
      std::string name = entry->d_name;
      if (name == "." || name == "..") continue;
      const auto path = relative.empty() ? name : relative + "/" + name;
      struct stat info {};
      if (lstat((root + "/" + path).c_str(), &info))
        throw std::runtime_error("inventory stat failed");
      if (S_ISDIR(info.st_mode))
        collect(root, path, files);
      else if (S_ISREG(info.st_mode))
        files.push_back(path);
      else
        throw std::runtime_error("unsupported inventory member");
    }
  } catch (...) {
    closedir(directory);
    throw;
  }
  closedir(directory);
}
std::vector<std::string> maintenance_files(const std::string& root) {
  std::vector<std::string> files;
  collect(root, "", files);
  std::sort(files.begin(), files.end());
  return files;
}
}  // namespace phantom
