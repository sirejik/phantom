#pragma once
#include <cstddef>
#include <cstdint>
#include <deque>
#include <string>
#include <vector>

namespace phantom {

// Structured diagnostic events for `phantom-controller`.
//
// The motor loop must never wait for a log write, so `emit` only formats into a
// bounded in-memory queue and `flush` performs one bounded non-blocking drain
// per tick. Losing lines is preferable to stalling the loop and is itself
// reported once per episode as LOG_STORAGE_DEGRADED.
class EventLog {
public:
  struct Field { std::string name, value; bool quoted; };

  EventLog() = default;
  // `stream_fd` normally is stdout, which systemd routes to the journal.
  void open(int stream_fd, const std::string& build_id, const std::string& boot_id_hex,
            const std::string& bundle_hash_hex, std::size_t capacity = 256) noexcept;
  void set_incident(const std::string& incident_id_hex) noexcept { incident_id_ = incident_id_hex; }

  void emit(std::uint64_t monotonic_us, const char* event_code, const char* subsystem,
            const std::vector<Field>& fields = std::vector<Field>()) noexcept;
  void emit_transition(std::uint64_t monotonic_us, const char* event_code, const char* subsystem,
                       std::uint16_t state_before, std::uint16_t state_after, std::uint16_t fault_code,
                       std::uint64_t command_sequence) noexcept;
  // Bounded drain; safe to call from the control loop.
  void flush() noexcept;

  std::uint64_t dropped() const noexcept { return dropped_; }
  bool degraded() const noexcept { return degraded_; }

  static std::string escape(const std::string& value);
  static Field text(const std::string& name, const std::string& value) { return Field{name, value, true}; }
  static Field number(const std::string& name, std::uint64_t value);
  static Field boolean(const std::string& name, bool value);

private:
  int fd_ = -1;
  std::size_t capacity_ = 256;
  std::deque<std::string> pending_;
  std::string build_id_, boot_id_, bundle_hash_, incident_id_, partial_;
  std::uint64_t dropped_ = 0;
  bool degraded_ = false, degraded_reported_ = false;
};

// Persistent "the controller is running" marker.  Present at startup means the
// previous run ended without a clean shutdown (crash, kill or power loss).
class RuntimeActiveMarker {
public:
  explicit RuntimeActiveMarker(const std::string& path) noexcept;
  bool previous_run_was_unclean() const noexcept { return previous_unclean_; }
  bool valid() const noexcept { return created_; }
  void clear() noexcept;
  ~RuntimeActiveMarker();

private:
  std::string path_;
  bool previous_unclean_ = false, created_ = false;
};

// Age and size bounded retention for a log directory or single log file.
// Returns the number of removed/truncated files.
std::size_t enforce_log_retention(const std::string& directory, std::uint32_t retention_days,
                                  std::uint32_t max_megabytes, std::uint64_t now_epoch_seconds) noexcept;

}  // namespace phantom
