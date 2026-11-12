// Wi-Fi de mentira. A bancada liga e desliga o "roteador"; o firmware vê WL_CONNECTED quando pediu
// conexão (WiFi.begin ou WiFiManager) e o roteador está ligado.
#pragma once
#include "Arduino.h"
#include "sim.h"

typedef enum {
  WL_NO_SHIELD = 255, WL_IDLE_STATUS = 0, WL_NO_SSID_AVAIL = 1, WL_SCAN_COMPLETED = 2, WL_CONNECTED = 3,
  WL_CONNECT_FAILED = 4, WL_CONNECTION_LOST = 5, WL_DISCONNECTED = 6
} wl_status_t;
typedef enum { WIFI_OFF = 0, WIFI_STA = 1, WIFI_AP = 2, WIFI_AP_STA = 3 } wifi_mode_t;
#define WIFI_MODE_STA WIFI_STA

class IPAddress {
 public:
  IPAddress(uint8_t a = 0, uint8_t b = 0, uint8_t c = 0, uint8_t d = 0) : o_{a, b, c, d} {}
  String toString() const {
    char t[16];
    snprintf(t, sizeof t, "%u.%u.%u.%u", o_[0], o_[1], o_[2], o_[3]);
    return String(t);
  }
  uint8_t operator[](int i) const { return o_[i]; }
 private:
  uint8_t o_[4];
};
inline Print &operator<<(Print &p, const IPAddress &ip) { p.print(ip.toString()); return p; }

class WiFiClass {
 public:
  wl_status_t begin(const char *ssid = "", const char *senha = nullptr, ...) {
    ssid_ = ssid ? ssid : "";
    (void)senha;
    sim::wifiPedirConexao();
    return status();
  }
  wl_status_t begin(const String &ssid, const String &senha) { return begin(ssid.c_str(), senha.c_str()); }
  wl_status_t status() {
    if (sim::wifiConectado()) {
      if (!avisouConexao_) {
        avisouConexao_ = true;
        sim::evento("\"t\":\"wifi\",\"conectado\":true");
      }
      return WL_CONNECTED;
    }
    if (avisouConexao_) {
      avisouConexao_ = false;
      sim::evento("\"t\":\"wifi\",\"conectado\":false");
    }
    return WL_DISCONNECTED;
  }
  bool isConnected() { return status() == WL_CONNECTED; }
  bool disconnect(bool = false, bool = false) { sim::wifiDesconectar(); return true; }
  bool reconnect() { sim::wifiPedirConexao(); return true; }
  bool mode(wifi_mode_t) { return true; }
  bool setAutoReconnect(bool) { return true; }
  bool setHostname(const char *) { return true; }
  bool setSleep(bool) { return true; }
  void persistent(bool) {}
  IPAddress localIP() { return isConnected() ? IPAddress(192, 168, 0, 42) : IPAddress(); }
  IPAddress gatewayIP() { return IPAddress(192, 168, 0, 1); }
  String SSID() { return String(ssid_.empty() ? "Oriki-Ponto" : ssid_.c_str()); }
  String macAddress() { return String("A4:CF:12:34:56:78"); }
  int8_t RSSI() { return isConnected() ? -58 : 0; }
  int16_t scanNetworks() { return sim::wifiDisponivel() ? 1 : 0; }

 private:
  std::string ssid_;
  bool avisouConexao_ = false;
};
extern WiFiClass WiFi;

#include "WiFiClient.h"
