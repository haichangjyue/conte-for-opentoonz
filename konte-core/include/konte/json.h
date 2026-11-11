// SPDX-License-Identifier: BSD-3-Clause
// konte-core: 零依赖 JSON（够用：解析 sceneplan/manifest、输出报告）
// 支持 object/array/string(含 \u 转义与代理对)/number/bool/null。
#pragma once
#ifndef KONTE_JSON_H
#define KONTE_JSON_H

#include <cstdint>
#include <cstdio>
#include <cctype>
#include <cmath>
#include <string>
#include <utility>
#include <vector>
#include <stdexcept>
#include <sstream>

namespace konte {

class JsonError : public std::runtime_error {
public:
  explicit JsonError(const std::string& m) : std::runtime_error(m) {}
};

class Json {
public:
  enum class Type { Null, Bool, Number, String, Array, Object };

  Json() : type_(Type::Null) {}
  explicit Json(bool b) : type_(Type::Bool), b_(b) {}
  explicit Json(double n) : type_(Type::Number), num_(n) {}
  explicit Json(const std::string& s) : type_(Type::String), s_(s) {}

  static Json object() { Json j; j.type_ = Type::Object; return j; }
  static Json array()  { Json j; j.type_ = Type::Array;  return j; }
  static Json integer(long long v) { Json j; j.type_ = Type::Number; j.num_ = (double)v; j.isInt_ = true; return j; }

  Type type() const { return type_; }
  bool isNull()   const { return type_ == Type::Null; }
  bool isBool()   const { return type_ == Type::Bool; }
  bool isNumber() const { return type_ == Type::Number; }
  bool isString() const { return type_ == Type::String; }
  bool isArray()  const { return type_ == Type::Array; }
  bool isObject() const { return type_ == Type::Object; }

  // ---- object ----
  bool contains(const std::string& k) const {
    for (auto& kv : obj_) if (kv.first == k) return true;
    return false;
  }
  const Json& at(const std::string& k) const {
    for (auto& kv : obj_) if (kv.first == k) return kv.second;
    throw JsonError("missing key: " + k);
  }
  Json& operator[](const std::string& k) {
    if (type_ != Type::Object) { type_ = Type::Object; }
    for (auto& kv : obj_) if (kv.first == k) return kv.second;
    obj_.emplace_back(k, Json());
    return obj_.back().second;
  }
  const std::vector<std::pair<std::string, Json>>& items() const { return obj_; }

  // ---- array ----
  size_t size() const {
    if (type_ == Type::Array) return arr_.size();
    if (type_ == Type::Object) return obj_.size();
    return 0;
  }
  const Json& operator[](size_t i) const {
    if (type_ != Type::Array || i >= arr_.size()) throw JsonError("array index out of range");
    return arr_[i];
  }
  void push_back(const Json& v) { if (type_ != Type::Array) type_ = Type::Array; arr_.push_back(v); }

  // ---- scalars ----
  bool asBool() const {
    if (type_ == Type::Bool) return b_;
    throw JsonError("not a bool");
  }
  long long asInt() const {
    if (type_ != Type::Number) throw JsonError("not a number");
    return (long long)std::llround(num_);
  }
  double asDouble() const {
    if (type_ != Type::Number) throw JsonError("not a number");
    return num_;
  }
  const std::string& asString() const {
    if (type_ != Type::String) throw JsonError("not a string");
    return s_;
  }
  std::string asStringOr(const std::string& d) const { return type_ == Type::String ? s_ : d; }

  // ---- parse ----
  static Json parse(const std::string& text) {
    Parser p(text);
    p.skipWs();
    Json v = p.parseValue();
    p.skipWs();
    if (!p.eof()) throw JsonError("trailing characters in JSON");
    return v;
  }

  // ---- dump ----
  std::string dump(int indent = -1) const {
    std::string out;
    dumpImpl(out, indent, 0);
    return out;
  }

private:
  Type type_ = Type::Null;
  bool b_ = false;
  double num_ = 0.0;
  bool isInt_ = false;
  std::string s_;
  std::vector<Json> arr_;
  std::vector<std::pair<std::string, Json>> obj_;

  static void appendUtf8(std::string& out, uint32_t cp) {
    if (cp <= 0x7F) out.push_back((char)cp);
    else if (cp <= 0x7FF) {
      out.push_back((char)(0xC0 | (cp >> 6)));
      out.push_back((char)(0x80 | (cp & 0x3F)));
    } else if (cp <= 0xFFFF) {
      out.push_back((char)(0xE0 | (cp >> 12)));
      out.push_back((char)(0x80 | ((cp >> 6) & 0x3F)));
      out.push_back((char)(0x80 | (cp & 0x3F)));
    } else {
      out.push_back((char)(0xF0 | (cp >> 18)));
      out.push_back((char)(0x80 | ((cp >> 12) & 0x3F)));
      out.push_back((char)(0x80 | ((cp >> 6) & 0x3F)));
      out.push_back((char)(0x80 | (cp & 0x3F)));
    }
  }

  static std::string escape(const std::string& s) {
    std::string o;
    for (unsigned char c : s) {
      switch (c) {
        case '"': o += "\\\""; break;
        case '\\': o += "\\\\"; break;
        case '\n': o += "\\n"; break;
        case '\r': o += "\\r"; break;
        case '\t': o += "\\t"; break;
        case '\b': o += "\\b"; break;
        case '\f': o += "\\f"; break;
        default:
          if (c < 0x20) { char buf[8]; std::snprintf(buf, sizeof buf, "\\u%04x", c); o += buf; }
          else o.push_back((char)c);
      }
    }
    return o;
  }

  void dumpImpl(std::string& out, int indent, int depth) const {
    auto nl = [&](int d) { if (indent >= 0) { out += "\n"; out += std::string((size_t)(indent * d), ' '); } };
    switch (type_) {
      case Type::Null: out += "null"; break;
      case Type::Bool: out += b_ ? "true" : "false"; break;
      case Type::Number: {
        std::ostringstream os;
        if (isInt_) os << (long long)std::llround(num_);
        else { os.precision(12); os << num_; }
        out += os.str();
        break;
      }
      case Type::String: out += "\"" + escape(s_) + "\""; break;
      case Type::Array: {
        out += "[";
        for (size_t i = 0; i < arr_.size(); ++i) {
          if (i) out += ",";
          nl(depth + 1);
          arr_[i].dumpImpl(out, indent, depth + 1);
        }
        if (!arr_.empty()) nl(depth);
        out += "]";
        break;
      }
      case Type::Object: {
        out += "{";
        for (size_t i = 0; i < obj_.size(); ++i) {
          if (i) out += ",";
          nl(depth + 1);
          out += "\"" + escape(obj_[i].first) + "\":";
          if (indent >= 0) out += " ";
          obj_[i].second.dumpImpl(out, indent, depth + 1);
        }
        if (!obj_.empty()) nl(depth);
        out += "}";
        break;
      }
    }
  }

  struct Parser {
    const std::string& t;
    size_t i = 0;
    explicit Parser(const std::string& s) : t(s) {}
    bool eof() const { return i >= t.size(); }
    char peek() const { if (eof()) throw JsonError("unexpected end"); return t[i]; }
    char get() { if (eof()) throw JsonError("unexpected end"); return t[i++]; }
    void skipWs() { while (!eof() && (t[i] == ' ' || t[i] == '\t' || t[i] == '\n' || t[i] == '\r')) ++i; }

    Json parseValue() {
      skipWs();
      if (eof()) throw JsonError("unexpected end");
      char c = peek();
      if (c == '{') return parseObject();
      if (c == '[') return parseArray();
      if (c == '"') return Json(parseString());
      if (c == 't') { expect("true"); return Json(true); }
      if (c == 'f') { expect("false"); return Json(false); }
      if (c == 'n') { expect("null"); return Json(); }
      return parseNumber();
    }
    void expect(const char* lit) {
      for (const char* p = lit; *p; ++p) { if (eof() || get() != *p) throw JsonError("bad literal"); }
    }
    Json parseObject() {
      Json o = Json::object();
      get(); // {
      skipWs();
      if (!eof() && peek() == '}') { get(); return o; }
      while (true) {
        skipWs();
        if (peek() != '"') throw JsonError("expected object key");
        std::string k = parseString();
        skipWs();
        if (get() != ':') throw JsonError("expected ':'");
        Json v = parseValue();
        o[k] = v;
        skipWs();
        char c = get();
        if (c == '}') break;
        if (c != ',') throw JsonError("expected ',' or '}'");
      }
      return o;
    }
    Json parseArray() {
      Json a = Json::array();
      get(); // [
      skipWs();
      if (!eof() && peek() == ']') { get(); return a; }
      while (true) {
        a.push_back(parseValue());
        skipWs();
        char c = get();
        if (c == ']') break;
        if (c != ',') throw JsonError("expected ',' or ']'");
      }
      return a;
    }
    std::string parseString() {
      if (get() != '"') throw JsonError("expected string");
      std::string out;
      while (true) {
        char c = get();
        if (c == '"') break;
        if (c == '\\') {
          char e = get();
          switch (e) {
            case '"': out.push_back('"'); break;
            case '\\': out.push_back('\\'); break;
            case '/': out.push_back('/'); break;
            case 'b': out.push_back('\b'); break;
            case 'f': out.push_back('\f'); break;
            case 'n': out.push_back('\n'); break;
            case 'r': out.push_back('\r'); break;
            case 't': out.push_back('\t'); break;
            case 'u': {
              uint32_t cp = parseHex4();
              if (cp >= 0xD800 && cp <= 0xDBFF) {
                if (!eof() && peek() == '\\') {
                  size_t save = i; get();
                  if (!eof() && peek() == 'u') {
                    get();
                    uint32_t lo = parseHex4();
                    cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                  } else { i = save; }
                }
              }
              appendUtf8(out, cp);
              break;
            }
            default: throw JsonError("bad escape");
          }
        } else {
          out.push_back(c);
        }
      }
      return out;
    }
    uint32_t parseHex4() {
      uint32_t v = 0;
      for (int k = 0; k < 4; ++k) {
        char c = get();
        v <<= 4;
        if (c >= '0' && c <= '9') v |= (c - '0');
        else if (c >= 'a' && c <= 'f') v |= (c - 'a' + 10);
        else if (c >= 'A' && c <= 'F') v |= (c - 'A' + 10);
        else throw JsonError("bad hex");
      }
      return v;
    }
    Json parseNumber() {
      size_t start = i;
      if (!eof() && (peek() == '-' )) ++i;
      while (!eof() && (isdigit((unsigned char)t[i]) || t[i] == '.' || t[i] == 'e' || t[i] == 'E' || t[i] == '+' || t[i] == '-')) ++i;
      if (i == start) throw JsonError("bad number");
      std::string s = t.substr(start, i - start);
      bool isInt = s.find_first_of(".eE") == std::string::npos;
      double d = std::strtod(s.c_str(), nullptr);
      Json j(d);
      j.isInt_ = isInt;
      return j;
    }
  };
};

}  // namespace konte

#endif  // KONTE_JSON_H
