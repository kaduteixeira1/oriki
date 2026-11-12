// O que o core do ESP32 já traz junto com o Arduino.h: objeto ESP, hora pela internet (configTime).
#pragma once
#include <ctime>

class EspClass {
 public:
  void restart();
  uint32_t getFreeHeap() { return 200000; }
  uint32_t getHeapSize() { return 320000; }
  uint64_t getEfuseMac() { return 0x0000A4CF12345678ULL; }
  const char *getChipModel() { return "ESP32 (simulado)"; }
  uint32_t getCpuFreqMHz() { return 240; }
  const char *getSdkVersion() { return "oriki-simulador"; }
};
extern EspClass ESP;
uint32_t esp_random();
void esp_restart();

// Hora pela internet: depois do configTime, getLocalTime devolve a hora do PC no fuso pedido.
void configTime(long gmtOffsetSeg, int horarioVeraoSeg, const char *servidor1, const char *servidor2 = nullptr,
                const char *servidor3 = nullptr);
void configTzTime(const char *tz, const char *servidor1, const char *servidor2 = nullptr,
                  const char *servidor3 = nullptr);
bool getLocalTime(struct tm *info, uint32_t esperaMs = 5000);
