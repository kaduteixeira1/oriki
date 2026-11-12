#pragma once
#include "Arduino.h"
// I2C de mentira: o único dispositivo no barramento é o RTC DS3231 (0x68).
class TwoWire {
 public:
  bool begin(...) { return true; }
  void setClock(uint32_t) {}
  void beginTransmission(uint8_t endereco) { endereco_ = endereco; }
  uint8_t endTransmission(bool = true) { return endereco_ == 0x68 ? 0 : 2; }
  size_t write(uint8_t) { return 1; }
  uint8_t requestFrom(uint8_t, uint8_t n, bool = true) { return n; }
  int available() { return 0; }
  int read() { return 0; }
 private:
  uint8_t endereco_ = 0;
};
extern TwoWire Wire;
