#pragma once
#include "Arduino.h"
// Barramento OneWire de mentira: só serve para o DallasTemperature saber em que pino o sensor está.
class OneWire {
 public:
  OneWire() {}
  explicit OneWire(uint8_t pino) : pino_(pino) {}
  void begin(uint8_t pino) { pino_ = pino; }
  uint8_t reset() { return 1; }
  void reset_search() {}
  bool search(uint8_t *endereco) { (void)endereco; return false; }
  uint8_t pino() const { return pino_; }
 private:
  uint8_t pino_ = 0;
};
