// Preferences (NVS do ESP32) de mentira: um arquivo de texto por namespace em dados/<dispositivo>/nvs/.
#pragma once
#include "Arduino.h"
#include <map>

class Preferences {
 public:
  bool begin(const char *nome, bool somenteLeitura = false, const char * = nullptr);
  void end() { gravar(); nome_.clear(); }
  bool clear() { valores_.clear(); return gravar(); }
  bool remove(const char *chave) { valores_.erase(chave); return gravar(); }
  bool isKey(const char *chave) { return valores_.count(chave) > 0; }

  size_t putUInt(const char *k, uint32_t v) { return guardar(k, std::to_string(v)); }
  size_t putULong(const char *k, uint32_t v) { return guardar(k, std::to_string(v)); }
  size_t putULong64(const char *k, uint64_t v) { return guardar(k, std::to_string(v)); }
  size_t putInt(const char *k, int32_t v) { return guardar(k, std::to_string(v)); }
  size_t putLong(const char *k, int32_t v) { return guardar(k, std::to_string(v)); }
  size_t putShort(const char *k, int16_t v) { return guardar(k, std::to_string(v)); }
  size_t putUShort(const char *k, uint16_t v) { return guardar(k, std::to_string(v)); }
  size_t putUChar(const char *k, uint8_t v) { return guardar(k, std::to_string(v)); }
  size_t putChar(const char *k, int8_t v) { return guardar(k, std::to_string(v)); }
  size_t putBool(const char *k, bool v) { return guardar(k, v ? "1" : "0"); }
  size_t putFloat(const char *k, float v) { return guardar(k, std::to_string(v)); }
  size_t putDouble(const char *k, double v) { return guardar(k, std::to_string(v)); }
  size_t putString(const char *k, const char *v) { return guardar(k, v); }
  size_t putString(const char *k, const String &v) { return guardar(k, v.std()); }

  uint32_t getUInt(const char *k, uint32_t p = 0) { return isKey(k) ? (uint32_t)std::stoul(valores_[k]) : p; }
  uint32_t getULong(const char *k, uint32_t p = 0) { return getUInt(k, p); }
  uint64_t getULong64(const char *k, uint64_t p = 0) { return isKey(k) ? std::stoull(valores_[k]) : p; }
  int32_t getInt(const char *k, int32_t p = 0) { return isKey(k) ? std::stoi(valores_[k]) : p; }
  int32_t getLong(const char *k, int32_t p = 0) { return getInt(k, p); }
  int16_t getShort(const char *k, int16_t p = 0) { return (int16_t)getInt(k, p); }
  uint16_t getUShort(const char *k, uint16_t p = 0) { return (uint16_t)getUInt(k, p); }
  uint8_t getUChar(const char *k, uint8_t p = 0) { return (uint8_t)getUInt(k, p); }
  int8_t getChar(const char *k, int8_t p = 0) { return (int8_t)getInt(k, p); }
  bool getBool(const char *k, bool p = false) { return isKey(k) ? valores_[k] == "1" : p; }
  float getFloat(const char *k, float p = 0) { return isKey(k) ? std::stof(valores_[k]) : p; }
  double getDouble(const char *k, double p = 0) { return isKey(k) ? std::stod(valores_[k]) : p; }
  String getString(const char *k, const String &p = String()) { return isKey(k) ? String(valores_[k]) : p; }
  size_t getString(const char *k, char *saida, size_t n) {
    if (!isKey(k) || !n) return 0;
    String(valores_[k]).toCharArray(saida, (unsigned)n);
    return strlen(saida);
  }

 private:
  size_t guardar(const char *k, const std::string &v);
  bool gravar();
  std::string nome_;
  bool somenteLeitura_ = false;
  std::map<std::string, std::string> valores_;
};
