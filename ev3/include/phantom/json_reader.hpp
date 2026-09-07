#pragma once
#include <cstddef>
#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace phantom {

// Minimal bounded JSON reader for the generated runtime configuration.
//
// The controller previously matched configuration with substring searches,
// which cannot distinguish a real field from an identical byte sequence
// elsewhere in the document and cannot read a value at all.  Runtime safety and
// timing parameters are normative configuration, so they need an actual parser.
// This one is deliberately small: no allocation-heavy generality, bounded input
// size and nesting depth, and fail-closed on anything it does not understand.
class JsonValue {
public:
  enum class Kind { Null, Bool, Number, String, Array, Object };
  Kind kind = Kind::Null;
  bool boolean = false;
  double number = 0;
  bool number_is_integer = false;
  std::string text;
  std::vector<JsonValue> items;
  std::map<std::string, JsonValue> members;

  bool is_object() const { return kind == Kind::Object; }
  const JsonValue* find(const std::string& name) const;
  // Resolve a "/a/b/c" pointer-like path; returns nullptr when absent.
  const JsonValue* path(const std::string& slash_separated) const;
};

// Parses `text`. Returns false and fills `error` on malformed input, duplicate
// object keys, excessive nesting or excessive length.
bool parse_json(const std::string& text, JsonValue& out, std::string& error,
                std::size_t max_bytes = 262144, std::size_t max_depth = 32);

// Typed, range-checked accessors. Each returns false when the field is absent
// or has the wrong type/range, so callers stay fail-closed.
bool json_uint(const JsonValue& root, const std::string& path, std::uint64_t min,
               std::uint64_t max, std::uint64_t& out);
bool json_bool(const JsonValue& root, const std::string& path, bool& out);
bool json_string(const JsonValue& root, const std::string& path, std::string& out);

}  // namespace phantom
