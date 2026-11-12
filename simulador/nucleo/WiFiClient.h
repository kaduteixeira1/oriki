#pragma once
#include "Arduino.h"
// Clientes TCP/TLS de mentira: o HTTPClient é quem fala com a bancada; aqui só guardamos a configuração.
class WiFiClient {
 public:
  virtual ~WiFiClient() {}
  void setTimeout(uint32_t) {}
  void stop() {}
  bool connected() { return false; }
};

class WiFiClientSecure : public WiFiClient {
 public:
  void setCACert(const char *ca) { temCA_ = ca && *ca; }
  void setInsecure() { inseguro_ = true; }
  void setCertificate(const char *) {}
  void setPrivateKey(const char *) {}
  void setHandshakeTimeout(unsigned long) {}
  bool temCA() const { return temCA_; }
  bool inseguro() const { return inseguro_; }
 private:
  bool temCA_ = false;
  bool inseguro_ = false;
};
typedef WiFiClientSecure NetworkClientSecure;
typedef WiFiClient NetworkClient;
