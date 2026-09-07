#include "phantom/json_reader.hpp"
#include <cmath>
#include <cstdlib>

namespace phantom {
namespace {

class Parser {
public:
  Parser(const std::string& text, std::size_t max_depth) : text_(text), max_depth_(max_depth) {}

  bool parse(JsonValue& out, std::string& error) {
    skip();
    if (!value(out, 0)) { error = error_; return false; }
    skip();
    if (position_ != text_.size()) { error = "trailing bytes after JSON document"; return false; }
    return true;
  }

private:
  const std::string& text_;
  std::size_t position_ = 0;
  std::size_t max_depth_;
  std::string error_;

  bool fail(const char* message) { if (error_.empty()) error_ = message; return false; }
  void skip() { while (position_ < text_.size() && (text_[position_] == ' ' || text_[position_] == '\t' || text_[position_] == '\n' || text_[position_] == '\r')) ++position_; }
  bool literal(const char* word) {
    const std::size_t length = std::char_traits<char>::length(word);
    if (text_.compare(position_, length, word) != 0) return fail("unknown literal");
    position_ += length;
    return true;
  }

  bool string_value(std::string& out) {
    if (position_ >= text_.size() || text_[position_] != '"') return fail("expected string");
    ++position_;
    out.clear();
    while (position_ < text_.size()) {
      const char c = text_[position_++];
      if (c == '"') return true;
      if (c == '\\') {
        if (position_ >= text_.size()) return fail("truncated escape");
        const char escape = text_[position_++];
        switch (escape) {
          case '"': out.push_back('"'); break;
          case '\\': out.push_back('\\'); break;
          case '/': out.push_back('/'); break;
          case 'b': out.push_back('\b'); break;
          case 'f': out.push_back('\f'); break;
          case 'n': out.push_back('\n'); break;
          case 'r': out.push_back('\r'); break;
          case 't': out.push_back('\t'); break;
          case 'u': {
            if (position_ + 4 > text_.size()) return fail("truncated \\u escape");
            unsigned code = 0;
            for (int i = 0; i < 4; ++i) {
              const char digit = text_[position_++];
              code <<= 4;
              if (digit >= '0' && digit <= '9') code |= unsigned(digit - '0');
              else if (digit >= 'a' && digit <= 'f') code |= unsigned(digit - 'a' + 10);
              else if (digit >= 'A' && digit <= 'F') code |= unsigned(digit - 'A' + 10);
              else return fail("invalid \\u escape");
            }
            // Configuration identifiers are ASCII; anything wider is refused
            // rather than silently transcoded.
            if (code > 0x7f) return fail("non-ASCII \\u escape is not supported in configuration");
            out.push_back(char(code));
            break;
          }
          default: return fail("invalid escape");
        }
      } else if (static_cast<unsigned char>(c) < 0x20) {
        return fail("raw control character in string");
      } else {
        out.push_back(c);
      }
    }
    return fail("unterminated string");
  }

  bool number_value(JsonValue& out) {
    const std::size_t start = position_;
    if (position_ < text_.size() && text_[position_] == '-') ++position_;
    bool digits = false, fractional = false;
    while (position_ < text_.size()) {
      const char c = text_[position_];
      if (c >= '0' && c <= '9') { digits = true; ++position_; }
      else if (c == '.' || c == 'e' || c == 'E' || c == '+' || c == '-') { if (c != '+' && c != '-') fractional = true; if (c == 'e' || c == 'E') fractional = true; ++position_; }
      else break;
    }
    if (!digits) return fail("expected number");
    const std::string token = text_.substr(start, position_ - start);
    char* end = nullptr;
    const double parsed = std::strtod(token.c_str(), &end);
    if (end == token.c_str() || *end != '\0' || !std::isfinite(parsed)) return fail("invalid number");
    out.kind = JsonValue::Kind::Number;
    out.number = parsed;
    out.number_is_integer = !fractional;
    return true;
  }

  bool value(JsonValue& out, std::size_t depth) {
    if (depth > max_depth_) return fail("JSON nesting is too deep");
    if (position_ >= text_.size()) return fail("unexpected end of JSON");
    const char c = text_[position_];
    if (c == '{') {
      ++position_;
      out.kind = JsonValue::Kind::Object;
      skip();
      if (position_ < text_.size() && text_[position_] == '}') { ++position_; return true; }
      for (;;) {
        skip();
        std::string name;
        if (!string_value(name)) return false;
        if (out.members.find(name) != out.members.end()) return fail("duplicate object key");
        skip();
        if (position_ >= text_.size() || text_[position_] != ':') return fail("expected ':'");
        ++position_;
        skip();
        JsonValue child;
        if (!value(child, depth + 1)) return false;
        out.members[name] = child;
        skip();
        if (position_ < text_.size() && text_[position_] == ',') { ++position_; continue; }
        if (position_ < text_.size() && text_[position_] == '}') { ++position_; return true; }
        return fail("expected ',' or '}'");
      }
    }
    if (c == '[') {
      ++position_;
      out.kind = JsonValue::Kind::Array;
      skip();
      if (position_ < text_.size() && text_[position_] == ']') { ++position_; return true; }
      for (;;) {
        skip();
        JsonValue child;
        if (!value(child, depth + 1)) return false;
        out.items.push_back(child);
        skip();
        if (position_ < text_.size() && text_[position_] == ',') { ++position_; continue; }
        if (position_ < text_.size() && text_[position_] == ']') { ++position_; return true; }
        return fail("expected ',' or ']'");
      }
    }
    if (c == '"') { out.kind = JsonValue::Kind::String; return string_value(out.text); }
    if (c == 't') { if (!literal("true")) return false; out.kind = JsonValue::Kind::Bool; out.boolean = true; return true; }
    if (c == 'f') { if (!literal("false")) return false; out.kind = JsonValue::Kind::Bool; out.boolean = false; return true; }
    if (c == 'n') { if (!literal("null")) return false; out.kind = JsonValue::Kind::Null; return true; }
    return number_value(out);
  }
};

}  // namespace

const JsonValue* JsonValue::find(const std::string& name) const {
  if (kind != Kind::Object) return nullptr;
  const auto found = members.find(name);
  return found == members.end() ? nullptr : &found->second;
}

const JsonValue* JsonValue::path(const std::string& slash_separated) const {
  const JsonValue* current = this;
  std::size_t start = 0;
  while (start < slash_separated.size()) {
    if (slash_separated[start] == '/') { ++start; continue; }
    const std::size_t end = slash_separated.find('/', start);
    const std::string name = slash_separated.substr(start, end == std::string::npos ? std::string::npos : end - start);
    current = current->find(name);
    if (!current) return nullptr;
    if (end == std::string::npos) break;
    start = end + 1;
  }
  return current;
}

bool parse_json(const std::string& text, JsonValue& out, std::string& error,
                std::size_t max_bytes, std::size_t max_depth) {
  if (text.size() > max_bytes) { error = "JSON document exceeds the bounded size"; return false; }
  Parser parser(text, max_depth);
  return parser.parse(out, error);
}

bool json_uint(const JsonValue& root, const std::string& path, std::uint64_t min,
               std::uint64_t max, std::uint64_t& out) {
  const JsonValue* node = root.path(path);
  if (!node || node->kind != JsonValue::Kind::Number || !node->number_is_integer) return false;
  if (node->number < 0 || node->number > 1.8e19) return false;
  const std::uint64_t value = static_cast<std::uint64_t>(node->number);
  if (value < min || value > max) return false;
  out = value;
  return true;
}

bool json_bool(const JsonValue& root, const std::string& path, bool& out) {
  const JsonValue* node = root.path(path);
  if (!node || node->kind != JsonValue::Kind::Bool) return false;
  out = node->boolean;
  return true;
}

bool json_string(const JsonValue& root, const std::string& path, std::string& out) {
  const JsonValue* node = root.path(path);
  if (!node || node->kind != JsonValue::Kind::String) return false;
  out = node->text;
  return true;
}

}  // namespace phantom
