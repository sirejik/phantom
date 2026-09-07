#include "phantom/event_log.hpp"
#include <algorithm>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

namespace phantom {
namespace {
constexpr std::size_t kMaxDrainPerFlush = 8;
}

std::string EventLog::escape(const std::string& value) {
  std::string out;
  out.reserve(value.size() + 8);
  for (char c : value) {
    switch (c) {
      case '"': out += "\\\""; break;
      case '\\': out += "\\\\"; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      default:
        if (static_cast<unsigned char>(c) < 0x20) {
          char buffer[7];
          std::snprintf(buffer, sizeof(buffer), "\\u%04x", static_cast<unsigned char>(c));
          out += buffer;
        } else {
          out.push_back(c);
        }
    }
  }
  return out;
}

EventLog::Field EventLog::number(const std::string& name, std::uint64_t value) {
  char buffer[24];
  std::snprintf(buffer, sizeof(buffer), "%llu", (unsigned long long)value);
  return Field{name, buffer, false};
}

EventLog::Field EventLog::boolean(const std::string& name, bool value) {
  return Field{name, value ? "true" : "false", false};
}

void EventLog::open(int stream_fd, const std::string& build_id, const std::string& boot_id_hex,
                    const std::string& bundle_hash_hex, std::size_t capacity) noexcept {
  fd_ = stream_fd;
  capacity_ = capacity ? capacity : 1;
  build_id_ = build_id;
  boot_id_ = boot_id_hex;
  bundle_hash_ = bundle_hash_hex;
  if (fd_ >= 0) {
    const int flags = ::fcntl(fd_, F_GETFL, 0);
    if (flags >= 0) ::fcntl(fd_, F_SETFL, flags | O_NONBLOCK);
  }
}

void EventLog::emit(std::uint64_t monotonic_us, const char* event_code, const char* subsystem,
                    const std::vector<Field>& fields) noexcept {
  char header[192];
  std::snprintf(header, sizeof(header),
                "{\"event\":\"%s\",\"subsystem\":\"%s\",\"monotonic_us\":%llu",
                event_code, subsystem, (unsigned long long)monotonic_us);
  std::string line(header);
  line += ",\"controller_boot_id\":\"" + boot_id_ + "\"";
  line += ",\"build_id\":\"" + build_id_ + "\"";
  line += ",\"commissioning_bundle_hash\":\"" + bundle_hash_ + "\"";
  line += ",\"incident_id\":\"" + incident_id_ + "\"";
  for (const Field& field : fields) {
    line += ",\"" + field.name + "\":";
    if (field.quoted) line += "\"" + escape(field.value) + "\"";
    else line += field.value;
  }
  line += "}\n";
  if (pending_.size() >= capacity_) {
    pending_.pop_front();
    ++dropped_;
    degraded_ = true;
  }
  pending_.push_back(line);
}

void EventLog::emit_transition(std::uint64_t monotonic_us, const char* event_code, const char* subsystem,
                               std::uint16_t state_before, std::uint16_t state_after,
                               std::uint16_t fault_code, std::uint64_t command_sequence) noexcept {
  emit(monotonic_us, event_code, subsystem,
       {number("state_before", state_before), number("state_after", state_after),
        number("fault_code", fault_code), number("command_sequence", command_sequence)});
}

void EventLog::flush() noexcept {
  if (fd_ < 0) return;
  if (degraded_ && !degraded_reported_) {
    degraded_reported_ = true;
    // Reported through the same bounded queue; if that also drops, the counter
    // still carries the fact into telemetry and the flight recorder.
    emit(0, "LOG_STORAGE_DEGRADED", "LOGGER", {number("dropped_events", dropped_)});
  }
  for (std::size_t drained = 0; drained < kMaxDrainPerFlush; ++drained) {
    if (partial_.empty()) {
      if (pending_.empty()) return;
      partial_ = pending_.front();
      pending_.pop_front();
    }
    const ssize_t written = ::write(fd_, partial_.data(), partial_.size());
    if (written < 0) {
      if (errno == EINTR) continue;
      if (errno == EAGAIN || errno == EWOULDBLOCK) return;  // retry next tick
      partial_.clear();
      ++dropped_;
      degraded_ = true;
      return;
    }
    if (static_cast<std::size_t>(written) < partial_.size()) {
      partial_.erase(0, static_cast<std::size_t>(written));
      return;
    }
    partial_.clear();
  }
}

RuntimeActiveMarker::RuntimeActiveMarker(const std::string& path) noexcept : path_(path) {
  struct stat info;
  previous_unclean_ = ::stat(path_.c_str(), &info) == 0;
  int fd = ::open(path_.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0640);
  if (fd >= 0) {
    const char payload[] = "phantom-controller\n";
    created_ = ::write(fd, payload, sizeof(payload) - 1) == (ssize_t)(sizeof(payload) - 1);
    ::fsync(fd);
    ::close(fd);
  }
}

void RuntimeActiveMarker::clear() noexcept {
  if (!path_.empty()) ::unlink(path_.c_str());
  created_ = false;
}

RuntimeActiveMarker::~RuntimeActiveMarker() { clear(); }

std::size_t enforce_log_retention(const std::string& directory, std::uint32_t retention_days,
                                  std::uint32_t max_megabytes, std::uint64_t now_epoch_seconds) noexcept {
  DIR* handle = ::opendir(directory.c_str());
  if (!handle) return 0;
  struct Entry { std::string path; std::uint64_t modified; std::uint64_t size; };
  std::vector<Entry> entries;
  std::uint64_t total = 0;
  dirent* item;
  while ((item = ::readdir(handle))) {
    if (item->d_name[0] == '.') continue;
    const std::string path = directory + "/" + item->d_name;
    struct stat info;
    if (::stat(path.c_str(), &info) != 0 || !S_ISREG(info.st_mode)) continue;
    entries.push_back(Entry{path, (std::uint64_t)info.st_mtime, (std::uint64_t)info.st_size});
    total += (std::uint64_t)info.st_size;
  }
  ::closedir(handle);
  std::size_t removed = 0;
  const std::uint64_t horizon = (std::uint64_t)retention_days * 86400u;
  // Oldest first: age is enforced before the size ceiling.
  std::sort(entries.begin(), entries.end(),
            [](const Entry& a, const Entry& b) { return a.modified < b.modified; });
  const std::uint64_t ceiling = (std::uint64_t)max_megabytes * 1024u * 1024u;
  for (Entry& entry : entries) {
    const bool too_old = now_epoch_seconds > entry.modified && now_epoch_seconds - entry.modified > horizon;
    if (!too_old && total <= ceiling) continue;
    if (::unlink(entry.path.c_str()) == 0) { total -= entry.size; entry.size = 0; ++removed; }
  }
  return removed;
}

}  // namespace phantom
