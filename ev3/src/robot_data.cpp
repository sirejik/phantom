#include "phantom/robot_data.hpp"
#include "network_only_session.hpp"
#include <cerrno>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace phantom {
const char* network_only_descriptor_json() noexcept {
  return session::kNetworkOnlyDescriptorJson;
}

bool load_robot_data(const std::string& path, bool allow_network_only,
                     JsonValue& document, std::string& bytes, std::string& error) {
  bytes.clear();
  const int fd = path.empty() ? -1 : ::open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
  const int open_error = errno;
  if (fd < 0) {
    if (!allow_network_only || (!path.empty() && open_error != ENOENT)) {
      error = "robot data unavailable; calibration is required"; return false;
    }
    bytes = network_only_descriptor_json();
  } else {
    struct stat info {};
    if (::fstat(fd, &info) || !S_ISREG(info.st_mode) || info.st_size > 131072) {
      ::close(fd); error = "invalid robot data file"; return false;
    }
    char block[4096];
    for (;;) {
      const auto count = ::read(fd, block, sizeof(block));
      if (count < 0 && errno == EINTR) continue;
      if (count < 0 || bytes.size() + static_cast<std::size_t>(count) > 131072) {
        ::close(fd); error = "cannot read bounded robot data"; return false;
      }
      if (!count) break;
      bytes.append(block, static_cast<std::size_t>(count));
    }
    ::close(fd);
    if (!bytes.empty() && bytes.back() == '\n') bytes.pop_back();
  }
  if (!parse_json(bytes, document, error) || !document.is_object()) {
    error = "malformed robot data: " + error; return false;
  }
  error.clear(); return true;
}
}
