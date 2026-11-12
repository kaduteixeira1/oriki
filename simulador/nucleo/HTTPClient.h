// HTTPClient de mentira: o pedido vai para a bancada, que o repassa para a API de verdade
// (trocando o endereço do firmware pelo "endereço da API" configurado no painel).
// Com o Wi-Fi desligado, POST/GET devolvem -1, como o ESP32 sem rede.
#pragma once
#include "Arduino.h"
#include "WiFi.h"
#include "sim.h"
#include <vector>

#define HTTP_CODE_OK 200
#define HTTP_CODE_CREATED 201
#define HTTP_CODE_NO_CONTENT 204
#define HTTP_CODE_BAD_REQUEST 400
#define HTTP_CODE_UNAUTHORIZED 401
#define HTTP_CODE_FORBIDDEN 403
#define HTTP_CODE_NOT_FOUND 404
#define HTTP_CODE_UNPROCESSABLE_ENTITY 422
#define HTTP_CODE_TOO_MANY_REQUESTS 429
#define HTTP_CODE_INTERNAL_SERVER_ERROR 500
#define HTTPC_ERROR_CONNECTION_REFUSED (-1)
#define HTTPC_ERROR_SEND_HEADER_FAILED (-2)
#define HTTPC_ERROR_SEND_PAYLOAD_FAILED (-3)
#define HTTPC_ERROR_NOT_CONNECTED (-4)
#define HTTPC_ERROR_CONNECTION_LOST (-5)
#define HTTPC_ERROR_NO_STREAM (-6)
#define HTTPC_ERROR_NO_HTTP_SERVER (-7)
#define HTTPC_ERROR_TOO_LESS_RAM (-8)
#define HTTPC_ERROR_ENCODING (-9)
#define HTTPC_ERROR_STREAM_WRITE (-10)
#define HTTPC_ERROR_READ_TIMEOUT (-11)

class HTTPClient {
 public:
  bool begin(const String &url) { url_ = url.std(); cabecalhos_.clear(); return true; }
  bool begin(const char *url) { return begin(String(url)); }
  bool begin(WiFiClient &, const String &url) { return begin(url); }
  bool begin(WiFiClient &, const char *url) { return begin(String(url)); }
  void addHeader(const String &nome, const String &valor, bool = false, bool = true) {
    cabecalhos_.push_back({nome.std(), valor.std()});
  }
  void setTimeout(uint16_t ms) { timeout_ = ms; }
  void setConnectTimeout(int32_t) {}
  void setReuse(bool) {}
  void setUserAgent(const String &) {}
  void useHTTP10(bool = true) {}
  int GET() { return sendRequest("GET", ""); }
  int POST(const String &corpo) { return sendRequest("POST", corpo); }
  int POST(const uint8_t *corpo, size_t n) { return sendRequest("POST", String(std::string((const char *)corpo, n))); }
  int PUT(const String &corpo) { return sendRequest("PUT", corpo); }
  int PATCH(const String &corpo) { return sendRequest("PATCH", corpo); }
  int sendRequest(const char *metodo, const String &corpo) {
    codigo_ = sim::http(metodo, url_, cabecalhos_, corpo.std(), resposta_, timeout_);
    return codigo_;
  }
  String getString() { return String(resposta_); }
  int getSize() { return (int)resposta_.size(); }
  void end() {}
  bool connected() { return false; }
  static String errorToString(int erro) {
    switch (erro) {
      case HTTPC_ERROR_CONNECTION_REFUSED: return "connection refused";
      case HTTPC_ERROR_READ_TIMEOUT: return "read Timeout";
      case HTTPC_ERROR_CONNECTION_LOST: return "connection lost";
      default: return String("erro ") + String(erro);
    }
  }

 private:
  std::string url_;
  std::vector<std::pair<std::string, std::string>> cabecalhos_;
  std::string resposta_;
  int codigo_ = 0;
  uint16_t timeout_ = 5000;
};
