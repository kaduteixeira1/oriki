// WiFiManager de mentira: o "portal de configuração" já vem resolvido; conecta quando o roteador da
// bancada está ligado.
#pragma once
#include "Arduino.h"
#include "WiFi.h"

class WiFiManager {
 public:
  bool autoConnect(const char * = nullptr, const char * = nullptr) {
    WiFi.begin();
    unsigned long inicio = millis();
    while (millis() - inicio < 3000 && WiFi.status() != WL_CONNECTED) delay(50);
    return WiFi.status() == WL_CONNECTED;
  }
  bool startConfigPortal(const char *nome = nullptr, const char *senha = nullptr) { return autoConnect(nome, senha); }
  void setConfigPortalTimeout(unsigned long) {}
  void setConnectTimeout(unsigned long) {}
  void setConfigPortalBlocking(bool) {}
  void setDebugOutput(bool) {}
  void setTitle(const String &) {}
  void resetSettings() {}
  void process() {}
  String getWiFiSSID() { return WiFi.SSID(); }
};
