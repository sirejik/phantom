#include <arpa/inet.h>
#include <glob.h>
#include <grp.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <chrono>
#include <ctime>
#include <sstream>
#include <stdexcept>
#include <thread>

#include "phantom/byte_codec.hpp"
#include "phantom/maintenance.hpp"
#include "phantom/network_wire.hpp"
namespace phantom {
namespace {
const std::string root = "/opt/phantom/current";
std::uint64_t now() {
  return std::chrono::duration_cast<std::chrono::microseconds>(
             std::chrono::steady_clock::now().time_since_epoch())
      .count();
}
std::string text(const std::string& path) {
  auto value = read_bounded_file(path);
  while (!value.empty() && (value.back() == '\n' || value.back() == '\r'))
    value.pop_back();
  return value;
}
std::vector<std::string> paths(const char* pattern) {
  glob_t found{};
  std::vector<std::string> result;
  if (glob(pattern, 0, nullptr, &found) == 0)
    for (std::size_t i = 0; i < found.gl_pathc; ++i)
      result.emplace_back(found.gl_pathv[i]);
  globfree(&found);
  return result;
}
bool zero() {
  for (const auto& motor : paths("/sys/class/tacho-motor/motor*"))
    if (!maintenance_motor_stationary(
            text(motor + "/duty_cycle_sp"), text(motor + "/duty_cycle"),
            text(motor + "/speed"), text(motor + "/state"),
            text(motor + "/stop_action")))
      return false;
  return true;
}
bool active(const std::string& unit) {
  return maintenance_command({"systemctl", "is-active", "--quiet", unit}, 5)
             .code == 0;
}
struct Socket {
  int fd;
  explicit Socket(int socket) : fd(socket) {
    if (fd < 0) throw std::runtime_error("socket failed");
  }
  ~Socket() { close(fd); }
};
bool mdns(const std::string& robot, const std::string& boot) {
  Socket socket(::socket(AF_INET, SOCK_DGRAM, 0));
  int reuse = 1;
  setsockopt(socket.fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
  sockaddr_in bind_addr{};
  bind_addr.sin_family = AF_INET;
  bind_addr.sin_port = htons(5353);
  if (bind(socket.fd, reinterpret_cast<sockaddr*>(&bind_addr),
           sizeof(bind_addr)))
    return false;
  ip_mreq membership{};
  membership.imr_multiaddr.s_addr = inet_addr("224.0.0.251");
  membership.imr_interface.s_addr = INADDR_ANY;
  if (setsockopt(socket.fd, IPPROTO_IP, IP_ADD_MEMBERSHIP, &membership,
                 sizeof(membership)))
    return false;
  Buffer query(12, 0);
  query[5] = 1;
  std::string name = "_phantom-ev3._udp.local";
  std::istringstream labels(name);
  std::string label;
  while (std::getline(labels, label, '.')) {
    query.push_back(static_cast<unsigned char>(label.size()));
    query.insert(query.end(), label.begin(), label.end());
  }
  query.insert(query.end(), {0, 0, 12, 0, 1});
  sockaddr_in dest{};
  dest.sin_family = AF_INET;
  dest.sin_port = htons(5353);
  dest.sin_addr.s_addr = inet_addr("224.0.0.251");
  const auto deadline = now() + 3000000;
  while (now() < deadline) {
    sendto(socket.fd, query.data(), query.size(), 0,
           reinterpret_cast<sockaddr*>(&dest), sizeof(dest));
    pollfd poller{socket.fd, POLLIN, 0};
    if (poll(&poller, 1, 400) > 0) {
      char data[4096];
      auto count = recv(socket.fd, data, sizeof(data), 0);
      if (count > 0) {
        std::string packet(data, static_cast<std::size_t>(count));
        if (packet.find("_phantom-ev3") != std::string::npos &&
            packet.find("robot_id=" + robot) != std::string::npos &&
            packet.find("controller_boot_id=" + boot) != std::string::npos)
          return true;
      }
    }
  }
  return false;
}
bool protocol(const JsonValue& config, const std::string& boot_hex) {
  NetworkCrypto crypto;
  auto key = read_control_key("/var/lib/phantom/secrets/control.psk");
  Socket socket(::socket(AF_INET, SOCK_DGRAM, 0));
  sockaddr_in destination{};
  destination.sin_family = AF_INET;
  destination.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  std::uint64_t port = 0;
  if (!json_uint(config, "network/listen_port_udp", 1, 65535, port))
    return false;
  destination.sin_port = htons(static_cast<unsigned short>(port));
  if (connect(socket.fd, reinterpret_cast<sockaddr*>(&destination),
              sizeof(destination)))
    return false;
  NetworkPacket hello;
  hello.type = wire::MessageType::HELLO;
  if (!parse_hex(boot_hex, hello.boot.data(), 16)) return false;
  hello.sender_us = now();
  hello.payload.resize(wire::kHelloPayloadBytes);
  const auto robot = maintenance_string(config, "robot_id");
  if (robot.size() > 31) return false;
  std::copy(robot.begin(), robot.end(), hello.payload.begin());
  auto nonce = crypto.random_id();
  std::copy(nonce.begin(), nonce.end(),
            hello.payload.begin() + wire::kHelloOffsetClientNonce);
  auto send_packet = [&](const NetworkPacket& packet) {
    auto bytes = encode_wire(crypto, key, packet);
    return send(socket.fd, bytes.data(), bytes.size(), 0) ==
           static_cast<ssize_t>(bytes.size());
  };
  auto receive = [&](NetworkPacket& packet, unsigned ms) {
    pollfd p{socket.fd, POLLIN, 0};
    if (poll(&p, 1, static_cast<int>(ms)) <= 0) return false;
    unsigned char bytes[1024];
    auto count = recv(socket.fd, bytes, sizeof(bytes), 0);
    return count > 0 &&
           decode_wire(crypto, key, bytes, static_cast<std::size_t>(count),
                       packet) == DecodeResult::Ok;
  };
  if (!send_packet(hello)) return false;
  NetworkPacket ack;
  const auto deadline = now() + 2000000;
  bool accepted = false;
  while (now() < deadline)
    if (receive(ack, 250) && ack.type == wire::MessageType::HELLO_ACK) {
      accepted = true;
      break;
    }
  if (!accepted || ack.payload.size() != wire::kHelloAckPayloadBytes ||
      !std::equal(nonce.begin(), nonce.end(), ack.payload.begin()) ||
      ack.session == NetworkId{} || ack.boot != hello.boot)
    return false;
  NetworkPacket ping;
  ping.type = wire::MessageType::PING;
  ping.boot = hello.boot;
  ping.session = ack.session;
  ping.sequence = 1;
  ping.sender_us = now();
  ping.payload.resize(wire::kPingPayloadBytes);
  bytes::put64(ping.payload.data(), 7341);
  bytes::put64(ping.payload.data() + 8, 0x12345678);
  if (!send_packet(ping)) return false;
  bool pong = false, telemetry = false;
  const auto until = now() + 2000000;
  while (now() < until && !(pong && telemetry)) {
    NetworkPacket packet;
    if (!receive(packet, 250) || packet.boot != hello.boot ||
        packet.session != ack.session)
      continue;
    if (packet.type == wire::MessageType::PONG)
      pong = packet.payload == ping.payload;
    if (packet.type == wire::MessageType::TELEMETRY &&
        packet.payload.size() == wire::kTelemetryPayloadBytes) {
      telemetry =
          bytes::u16(packet.payload.data() + wire::kTelemetryOffsetState) == 3;
      for (std::size_t i = 0; i < 12; ++i)
        telemetry = telemetry &&
                    packet.payload[wire::kTelemetryOffsetQActualRad + i] == 0;
      for (std::size_t i = 0; i < 4; ++i)
        telemetry = telemetry &&
                    packet.payload[wire::kTelemetryOffsetGripActual + i] == 0;
    }
  }
  if (!zero()) return false;
  NetworkPacket command = ping;
  command.type = wire::MessageType::COMMAND;
  command.sequence = 2;
  command.sender_us = now();
  command.payload.assign(wire::kCommandPayloadBytes, 0);
  bytes::put32(command.payload.data(), 5);
  bytes::putf(command.payload.data() + wire::kCommandOffsetQBaseRad, 0.1f);
  send_packet(command);
  auto corrupt = encode_wire(crypto, key, ping);
  corrupt.back() ^= 1;
  send(socket.fd, corrupt.data(), corrupt.size(), 0);
  send_packet(ping);
  std::this_thread::sleep_for(std::chrono::milliseconds(150));
  return pong && telemetry && zero();
}
}  // namespace
int maintenance_integration(const std::string& build_id) {
  const auto started = now();
  std::string checks = "[";
  bool pass = true;
  auto add = [&](const std::string& id, bool okay, const std::string& detail) {
    if (checks.size() > 1) checks += ",";
    checks += "{\"test_id\":" + maintenance_quote(id) +
              ",\"status\":" + maintenance_quote(okay ? "PASS" : "FAIL") +
              ",\"detail\":" + maintenance_quote(detail) + "}";
    pass = pass && okay;
  };
  std::string profile = "UNKNOWN";
  try {
    if (getuid() != 0) throw std::runtime_error("root required");
    auto manifest = maintenance_json(root + "/build-manifest.json");
    profile = maintenance_string(manifest, "build_profile");
    if (maintenance_string(manifest, "build_id") != build_id)
      throw std::runtime_error("installed identity mismatch");
    maintenance_validate_bundle(root);
    add("installed-config-bundle-identity", true,
        "installed bytes and identity verified");
    auto config = maintenance_json(root + "/config.generated.json");
    std::uint64_t scope = 1, observe = 1;
    bool qualification = false;
    if (!json_uint(config, "actuator_scope_mask", 0, 0, scope) ||
        !json_uint(config, "safety_observation_mask", 0, 0, observe) ||
        !json_bool(config, "qualification_only", qualification) ||
        !qualification || profile != "Diagnostic")
      throw std::runtime_error(
          "integration requires network-only Diagnostic scope zero");
    add("installed-artifact-integrity",
        maintenance_command(
            {"sh", "-c", "cd /opt/phantom/current && sha256sum -c SHA256SUMS"},
            30)
                .code == 0,
        "checksum inventory");
    const auto clock = maintenance_command(
        {"timedatectl", "show", "-p", "NTPSynchronized"}, 5);
    add("ev3-wall-clock", true,
        maintenance_clock_trust(
            static_cast<std::uint64_t>(std::time(nullptr)),
            clock.code == 0 &&
                clock.output.find("NTPSynchronized=yes") != std::string::npos));
    bool usb = false;
    for (const auto& vendor : paths("/sys/bus/usb/devices/*/idVendor")) {
      auto base = vendor.substr(0, vendor.rfind('/'));
      if (text(vendor) == "0846" && text(base + "/idProduct") == "9030")
        usb = true;
    }
    auto wireless = paths("/sys/class/net/*/wireless");
    add("ev3-wna1100",
        usb && wireless.size() == 1 &&
            maintenance_command({"lsmod"}, 5).output.find("ath9k_htc") !=
                std::string::npos,
        "USB adapter and driver");
    if (wireless.size() == 1) {
      auto wifi = wireless[0].substr(0, wireless[0].rfind('/'));
      auto interface = wifi.substr(wifi.rfind('/') + 1);
      add("ev3-wifi-dhcp",
          text(wifi + "/carrier") == "1" &&
              maintenance_command(
                  {"ip", "-o", "-4", "addr", "show", "dev", interface}, 5)
                      .output.find(" inet ") != std::string::npos,
          "association and IPv4");
    } else
      add("ev3-wifi-dhcp", false, "wireless interface unavailable");
    add("ev3-battery-telemetry",
        std::stoll(
            text("/sys/class/power_supply/lego-ev3-battery/voltage_now")) > 0,
        "battery voltage");
    for (const auto& binary : {"phantom-controller", "phantom-safety"})
      add(std::string(binary) + "-on-device-self-test",
          maintenance_command({root + "/bin/" + binary, "--self-test"}, 15)
                  .code == 0,
          "native self-test");
    bool services = true;
    for (const auto& unit :
         {"phantom-safety.service", "phantom-controller.service",
          "phantom-network.service", "phantom-mdns.service",
          "phantom-wifi-autoconnect.service"})
      services = active(unit) && services;
    add("ev3-systemd-startup", services, "installed services active");
    bool identity = true;
    for (const auto& entry : std::vector<std::pair<std::string, std::string>>{
             {"phantom-controller.service", "phantom-ctrl"},
             {"phantom-network.service", "phantom-net"},
             {"phantom-mdns.service", "phantom-mdns"}})
      identity =
          identity &&
          maintenance_command({"systemctl", "show", "-p", "User", entry.first},
                              5)
                  .output.find("User=" + entry.second) != std::string::npos;
    add("ev3-runtime-identities", identity, "distinct service users");
    bool ipc = true;
    for (const auto& path : {"/run/phantom/controller/network.sock",
                             "/run/phantom/network/controller.sock"}) {
      struct stat info {};
      auto group = getgrnam("phantom-ipc");
      ipc = ipc && group && stat(path, &info) == 0 &&
            (info.st_mode & 0777) == 0660 && info.st_gid == group->gr_gid;
    }
    add("ev3-controller-network-ipc-permissions", ipc, "IPC mode and group");
    bool privileges =
        maintenance_command({"runuser", "-u", "phantom-net", "--", "test", "!",
                             "-w", "/run/phantom/motor-control.lock"},
                            5)
            .code == 0;
    for (const auto& user : {"phantom-ctrl", "phantom-mdns"})
      privileges =
          maintenance_command({"runuser", "-u", user, "--", "test", "!", "-r",
                               "/var/lib/phantom/secrets/control.psk"},
                              5)
                  .code == 0 &&
          privileges;
    add("ev3-privilege-separation", privileges, "motor and secret permissions");
    add("ev3-zero-output-startup", zero(), "stationary outputs and BRAKE");
    auto boot = text("/run/phantom/controller/boot-id");
    if (!pass || !services || !zero())
      throw std::runtime_error("restart prerequisites failed");
    struct stat before {
    }, after{};
    stat("/var/log/phantom/safety-emergency.log", &before);
    bool killed =
        maintenance_command({"systemctl", "kill", "--signal=SIGKILL",
                             "--kill-who=main", "phantom-controller.service"},
                            5)
            .code == 0;
    const auto takeover_until = now() + 1500000;
    while (now() < takeover_until) {
      stat("/var/log/phantom/safety-emergency.log", &after);
      if (after.st_size > before.st_size) break;
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    add("ev3-supervisor-takeover",
        killed && zero() && after.st_size > before.st_size,
        "controller failure detected without motion");
    bool restarted =
        maintenance_command({"systemctl", "restart", "phantom.target"}, 120)
            .code == 0;
    add("ev3-safe-restart",
        restarted && active("phantom-controller.service") &&
            active("phantom-safety.service"),
        "services restarted");
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    auto fresh = text("/run/phantom/controller/boot-id");
    unsigned char parsed[16];
    add("ev3-controller-boot-id-rotation",
        fresh != boot && parse_hex(fresh, parsed, 16), "boot identity rotated");
    add("ev3-dns-sd-stage3",
        mdns(maintenance_string(config, "robot_id"), fresh), "live DNS-SD");
    add("ev3-udp-session-stage3", protocol(config, fresh),
        "HELLO, PONG, telemetry, scope-zero command");
    std::this_thread::sleep_for(std::chrono::milliseconds(1100));
    auto status = maintenance_json("/run/phantom/network/status.json");
    std::uint64_t hmac = 0, replay = 0, rejected = 0;
    add("ev3-network-security-stage3",
        json_uint(status, "counters/hmac_fail", 1, UINT64_MAX, hmac) &&
            json_uint(status, "counters/replay_reject", 1, UINT64_MAX, replay),
        "invalid authentication and replay rejected");
    add("ev3-stage3-zero-output-audit",
        zero() && privileges &&
            json_uint(status, "counters/motor_write_attempts_rejected", 0,
                      UINT64_MAX, rejected),
        "no output and no network motor authority");
  } catch (const std::exception& error) {
    add("device-integration-runner", false, error.what());
  }
  bool stationary = false;
  try {
    stationary = zero();
  } catch (...) {
  }
  if (!stationary) pass = false;
  const std::string report =
      "{\"schema_version\":2,\"phase\":\"DEVICE INTEGRATION "
      "TEST\",\"component\":\"EV3\",\"profile\":" +
      maintenance_quote(profile) +
      ",\"build_id\":" + maintenance_quote(build_id) +
      ",\"status\":" + maintenance_quote(pass ? "PASS" : "FAIL") +
      ",\"reason\":" +
      maintenance_quote(pass ? "COMPLETED" : "DEVICE_CHECK_FAILED") +
      ",\"duration_ms\":" + std::to_string((now() - started) / 1000) +
      ",\"terminal_state\":" +
      maintenance_quote(stationary ? "ZERO_OUTPUT_BRAKE"
                                   : "SAFE_STATE_UNVERIFIED") +
      ",\"hardware_evidence_state\":\"DEVICE\",\"checks\":" + checks + "]}";
  maintenance_write("/var/lib/phantom/device-integration-test.json", report);
  return pass ? 0 : 1;
}
}  // namespace phantom
