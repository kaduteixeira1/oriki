// DS18B20 de mentira: lê a temperatura da água da bancada virtual.
// "Sensor desconectado" na bancada faz getTempC devolver DEVICE_DISCONNECTED_C (-127), como o real.
#pragma once
#include "Arduino.h"
#include "OneWire.h"
#include "sim.h"

#define DEVICE_DISCONNECTED_C -127
#define DEVICE_DISCONNECTED_F -196.6
#define DEVICE_DISCONNECTED_RAW -7040
typedef uint8_t DeviceAddress[8];

class DallasTemperature {
 public:
  DallasTemperature() {}
  explicit DallasTemperature(OneWire *) {}
  void setOneWire(OneWire *) {}
  void begin() {}
  uint8_t getDeviceCount() { return sim::sensorConectado() ? 1 : 0; }
  uint8_t getDS18Count() { return getDeviceCount(); }
  bool getAddress(uint8_t *endereco, uint8_t indice) {
    if (indice != 0 || !sim::sensorConectado()) return false;
    const uint8_t falso[8] = {0x28, 0x4F, 0x52, 0x4B, 0x30, 0x31, 0x00, 0x9A};
    memcpy(endereco, falso, 8);
    return true;
  }
  bool isConnected(const uint8_t *) { return sim::sensorConectado(); }
  void setResolution(uint8_t bits) { resolucao_ = bits; }
  void setResolution(const uint8_t *, uint8_t bits) { resolucao_ = bits; }
  uint8_t getResolution() { return resolucao_; }
  void setWaitForConversion(bool) {}
  bool isConversionComplete() { return true; }
  void requestTemperatures() {}
  bool requestTemperaturesByIndex(uint8_t) { return true; }
  bool requestTemperaturesByAddress(const uint8_t *) { return true; }
  float getTempCByIndex(uint8_t indice) { return indice == 0 ? ler() : DEVICE_DISCONNECTED_C; }
  float getTempC(const uint8_t *) { return ler(); }
  float getTempFByIndex(uint8_t i) { float c = getTempCByIndex(i); return c <= DEVICE_DISCONNECTED_C ? DEVICE_DISCONNECTED_F : c * 1.8f + 32; }
  static float toFahrenheit(float c) { return c * 1.8f + 32; }

 private:
  // O DS18B20 entrega degraus de 0,0625 °C em 12 bits (0,5 °C em 9 bits).
  float ler() {
    if (!sim::sensorConectado()) return DEVICE_DISCONNECTED_C;
    float passo = 0.5f / (float)(1 << (resolucao_ - 9));
    return roundf(sim::temperaturaAgua() / passo) * passo;
  }
  uint8_t resolucao_ = 12;
};
