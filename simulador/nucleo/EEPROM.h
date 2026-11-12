// EEPROM guardada no arquivo dados/<dispositivo>/eeprom.bin (sobrevive a reiniciar o simulador).
// Uno: 1 KB, grava na hora. ESP32: tamanho do begin(n), grava no commit(), como na placa.
#pragma once
#include "Arduino.h"
#include <vector>

class EEPROMClass {
 public:
  bool begin(size_t tamanho);
  bool commit();
  void end() { commit(); }
  uint8_t read(int endereco);
  void write(int endereco, uint8_t valor);
  void update(int endereco, uint8_t valor) { if (read(endereco) != valor) write(endereco, valor); }
  uint16_t length();
  template <class T> T &get(int endereco, T &t) {
    preparar();
    uint8_t *p = (uint8_t *)&t;
    for (size_t i = 0; i < sizeof(T); i++) p[i] = read(endereco + (int)i);
    return t;
  }
  template <class T> const T &put(int endereco, const T &t) {
    preparar();
    const uint8_t *p = (const uint8_t *)&t;
    for (size_t i = 0; i < sizeof(T); i++) dados_[endereco + i] = p[i];
    if (gravarNaHora_) commit();
    return t;
  }
  uint8_t &operator[](int endereco) { preparar(); return dados_[endereco]; }

 private:
  void preparar();
  std::vector<uint8_t> dados_;
  bool pronto_ = false;
#ifdef ORIKI_PLACA_UNO
  bool gravarNaHora_ = true;
#else
  bool gravarNaHora_ = false;
#endif
};
extern EEPROMClass EEPROM;
