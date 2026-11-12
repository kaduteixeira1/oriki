// Núcleo do simulador: main(), relógio, pinos, Serial, String e a conversa com a bancada.
//
// Protocolo (uma mensagem por linha):
//   firmware -> bancada (saída padrão): JSON, ex. {"t":"s","d":"texto do Serial"}
//   bancada -> firmware (entrada padrão):
//     T 81.25          temperatura da água no sensor
//     D 0|1            sensor desconectado / conectado
//     P <pino> 0|1|-1  nível forçado num pino de entrada (botão); -1 solta
//     W 0|1            roteador Wi-Fi desligado / ligado
//     R <segundos>     soma esse ajuste ao relógio RTC (atrasar/adiantar)
//     S <texto>        linha digitada no Monitor serial
//     H <id> <status> <corpo em hex>   resposta de um pedido HTTP
#include "Arduino.h"
#include "sim.h"

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <fstream>
#include <iostream>
#include <map>
#include <mutex>
#include <random>
#include <sstream>
#include <thread>
#include <sys/stat.h>
#ifdef _WIN32
#include <direct.h>
#include <fcntl.h>
#include <io.h>
#endif

using Relogio = std::chrono::steady_clock;

namespace {
std::mutex trava;                       // estado compartilhado com a thread da entrada
std::mutex travaSaida;
std::condition_variable avisoHttp;

Relogio::time_point inicioReal;
double velocidade = 1.0;
int64_t utcInicioMs = 0;
int64_t ajusteRtc = 0;                  // segundos somados à hora local de Belém
bool rtcSemBateria = false;

float temperatura = 25.0f;
bool sensorOk = true;
bool roteadorLigado = true;
std::atomic<bool> wifiPedido{false};
unsigned long wifiPedidoEm = 0;

int forcado[100];                       // nível imposto pela bancada (-1 = livre)
uint8_t modo[100];
uint8_t saida[100];
std::deque<char> entradaSerial;
std::map<int, std::pair<int, std::string>> respostasHttp;
int proximoIdHttp = 1;
std::string bufferSerial;
int bitsAdc =
#ifdef ORIKI_PLACA_UNO
    10;
#else
    12;
#endif

void emitir(const std::string &json) {
  std::lock_guard<std::mutex> g(travaSaida);
  std::fwrite(json.data(), 1, json.size(), stdout);
  std::fputc('\n', stdout);
  std::fflush(stdout);
}

void descarregarSerial(bool tudo) {
  if (bufferSerial.empty()) return;
  size_t corte = tudo ? bufferSerial.size() : bufferSerial.rfind('\n');
  if (corte == std::string::npos) return;
  if (!tudo) corte += 1;
  std::string parte = bufferSerial.substr(0, corte);
  bufferSerial.erase(0, corte);
  emitir("{\"t\":\"s\",\"d\":" + sim::json(parte) + "}");
}

std::string deHex(const std::string &h) {
  std::string r;
  for (size_t i = 0; i + 1 < h.size(); i += 2) r += (char)std::stoi(h.substr(i, 2), nullptr, 16);
  return r;
}

void lerEntrada() {
  std::string linha;
  while (std::getline(std::cin, linha)) {
    if (!linha.empty() && linha.back() == '\r') linha.pop_back();
    if (linha.empty()) continue;
    char c = linha[0];
    std::string resto = linha.size() > 2 ? linha.substr(2) : "";
    std::lock_guard<std::mutex> g(trava);
    try {
      if (c == 'T') temperatura = std::stof(resto);
      else if (c == 'D') sensorOk = resto == "1";
      else if (c == 'W') roteadorLigado = resto == "1";
      else if (c == 'R') ajusteRtc += std::stoll(resto);
      else if (c == 'P') {
        std::istringstream in(resto);
        int p, v;
        if (in >> p >> v && p >= 0 && p < 100) forcado[p] = v;
      } else if (c == 'S') {
        for (char ch : resto) entradaSerial.push_back(ch);
        entradaSerial.push_back('\n');
      } else if (c == 'H') {
        std::istringstream in(resto);
        int id, status;
        std::string hex;
        in >> id >> status >> hex;
        respostasHttp[id] = {status, deHex(hex)};
        avisoHttp.notify_all();
      }
    } catch (...) {
      // linha mal formada: ignora
    }
  }
  std::exit(0);  // a bancada fechou: o "dispositivo" desliga junto
}

void salvarAjusteRtc() {
  std::ofstream f(sim::caminhoDados("rtc.txt"));
  f << ajusteRtc << "\n";
}
}  // namespace

// =====================================================================
// sim::
// =====================================================================
namespace sim {
std::string pastaDados() {
  const char *p = std::getenv("ORIKI_DADOS");
  return p && *p ? p : "dados";
}
std::string caminhoDados(const std::string &relativo) {
  std::string r = pastaDados() + "/" + relativo;
  size_t barra = r.rfind('/');
  if (barra != std::string::npos) criarPastas(r.substr(0, barra));
  return r;
}
void criarPastas(const std::string &caminho) {
  std::string atual;
  for (size_t i = 0; i <= caminho.size(); i++) {
    if (i == caminho.size() || caminho[i] == '/') {
      if (!atual.empty()) {
#ifdef _WIN32
        _mkdir(atual.c_str());
#else
        mkdir(atual.c_str(), 0755);
#endif
      }
    }
    if (i < caminho.size()) atual += caminho[i];
  }
}

float temperaturaAgua() { std::lock_guard<std::mutex> g(trava); return temperatura; }
bool sensorConectado() { std::lock_guard<std::mutex> g(trava); return sensorOk; }
bool wifiDisponivel() { std::lock_guard<std::mutex> g(trava); return roteadorLigado; }
void wifiPedirConexao() {
  if (!wifiPedido) wifiPedidoEm = millis();
  wifiPedido = true;
}
bool wifiConectado() { return wifiPedido && wifiDisponivel() && millis() - wifiPedidoEm >= 800; }
void wifiDesconectar() { wifiPedido = false; }

int http(const std::string &metodo, const std::string &url,
         const std::vector<std::pair<std::string, std::string>> &cabecalhos, const std::string &corpo,
         std::string &resposta, unsigned long timeoutMs) {
  resposta.clear();
  if (!wifiConectado()) return -1;  // HTTPC_ERROR_CONNECTION_REFUSED
  descarregarSerial(true);
  int id;
  {
    std::lock_guard<std::mutex> g(trava);
    id = proximoIdHttp++;
  }
  std::string h = "[";
  for (size_t i = 0; i < cabecalhos.size(); i++) {
    if (i) h += ",";
    h += "[" + json(cabecalhos[i].first) + "," + json(cabecalhos[i].second) + "]";
  }
  h += "]";
  emitir("{\"t\":\"h\",\"id\":" + std::to_string(id) + ",\"m\":" + json(metodo) + ",\"u\":" + json(url) +
         ",\"c\":" + h + ",\"b\":" + json(corpo) + "}");
  std::unique_lock<std::mutex> g(trava);
  bool chegou = avisoHttp.wait_for(g, std::chrono::milliseconds(timeoutMs ? timeoutMs : 15000),
                                   [&] { return respostasHttp.count(id) > 0; });
  if (!chegou) return -11;  // HTTPC_ERROR_READ_TIMEOUT
  auto r = respostasHttp[id];
  respostasHttp.erase(id);
  resposta = r.second;
  return r.first;
}

// O relógio de parede anda no tempo real mesmo com a bancada acelerada: assim o RTC não fica
// "divergente" para o servidor. A duração do ciclo vem do millis(), que é acelerado.
int64_t utcAgora() {
  return std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch()).count();
}
int64_t rtcLocalAgora() {
  std::lock_guard<std::mutex> g(trava);
  return utcAgora() - 3 * 3600 + ajusteRtc;
}
void rtcAjustarLocal(int64_t localSegundos) {
  {
    std::lock_guard<std::mutex> g(trava);
    ajusteRtc = localSegundos - (utcAgora() - 3 * 3600);
    rtcSemBateria = false;
  }
  salvarAjusteRtc();
  evento("\"t\":\"rtc\",\"ajuste\":" + std::to_string(ajusteRtc));
}
bool rtcPerdeuEnergia() { return rtcSemBateria; }

void evento(const std::string &corpo) {
  descarregarSerial(true);
  emitir("{" + corpo + "}");
}

std::string json(const std::string &t) {
  std::string r = "\"";
  for (unsigned char c : t) {
    switch (c) {
      case '"': r += "\\\""; break;
      case '\\': r += "\\\\"; break;
      case '\n': r += "\\n"; break;
      case '\r': r += "\\r"; break;
      case '\t': r += "\\t"; break;
      default:
        if (c < 0x20) {
          char b[8];
          std::snprintf(b, sizeof b, "\\u%04x", c);
          r += b;
        } else {
          r += (char)c;
        }
    }
  }
  return r + "\"";
}
}  // namespace sim

// =====================================================================
// Tempo e pinos
// =====================================================================
unsigned long millis() {
  return (unsigned long)(std::chrono::duration<double, std::milli>(Relogio::now() - inicioReal).count() * velocidade);
}
unsigned long micros() {
  return (unsigned long)(std::chrono::duration<double, std::micro>(Relogio::now() - inicioReal).count() * velocidade);
}
void delay(unsigned long ms) {
  descarregarSerial(true);
  std::this_thread::sleep_for(std::chrono::microseconds((long long)(ms * 1000.0 / velocidade)));
}
void delayMicroseconds(unsigned int us) {
  std::this_thread::sleep_for(std::chrono::microseconds((long long)(us / velocidade)));
}
void yield() { descarregarSerial(true); }

static const char *nomeModo(uint8_t m) {
  switch (m) {
    case OUTPUT: return "OUTPUT";
    case INPUT_PULLUP: return "INPUT_PULLUP";
    case INPUT_PULLDOWN: return "INPUT_PULLDOWN";
    default: return "INPUT";
  }
}

void pinMode(uint8_t p, uint8_t m) {
  if (p >= 100) return;
  modo[p] = m;
  sim::evento("\"t\":\"m\",\"p\":" + std::to_string(p) + ",\"m\":\"" + nomeModo(m) + "\"");
}
void digitalWrite(uint8_t p, uint8_t v) {
  if (p >= 100) return;
  v = v ? 1 : 0;
  if (saida[p] == v) return;
  saida[p] = v;
  sim::evento("\"t\":\"p\",\"p\":" + std::to_string(p) + ",\"v\":" + std::to_string(v));
}
int digitalRead(uint8_t p) {
  if (p >= 100) return LOW;
  std::lock_guard<std::mutex> g(trava);
  if (forcado[p] >= 0) return forcado[p];
  if (modo[p] == OUTPUT) return saida[p];
  return modo[p] == INPUT_PULLUP ? HIGH : LOW;
}
// Qualquer entrada analógica lê um TMP36 na água: 500 mV a 0 °C, 10 mV/°C.
int analogRead(uint8_t) {
  float t = sim::temperaturaAgua();
#ifdef ORIKI_PLACA_UNO
  const double referencia = 5.0;
#else
  const double referencia = 3.3;
#endif
  double volts = sim::sensorConectado() ? 0.5 + t / 100.0 : 0.0;
  int maximo = (1 << bitsAdc) - 1;
  long v = lround(volts / referencia * (maximo + 1));
  return (int)constrain(v, 0L, (long)maximo);
}
void analogReadResolution(int bits) { bitsAdc = constrain(bits, 9, 12); }
void analogWrite(uint8_t p, int v) {
  sim::evento("\"t\":\"pwm\",\"p\":" + std::to_string(p) + ",\"v\":" + std::to_string(v));
}
void tone(uint8_t p, unsigned int f, unsigned long d) {
  sim::evento("\"t\":\"tom\",\"p\":" + std::to_string(p) + ",\"f\":" + std::to_string(f) +
              ",\"d\":" + std::to_string(d));
}
void noTone(uint8_t p) { sim::evento("\"t\":\"tom\",\"p\":" + std::to_string(p) + ",\"f\":0,\"d\":0"); }
void attachInterrupt(uint8_t, void (*)(void), int) {}
void detachInterrupt(uint8_t) {}

static std::mt19937 gerador(12345);
long random(long mx) { return mx <= 0 ? 0 : (long)(gerador() % (unsigned long)mx); }
long random(long mn, long mx) { return mx <= mn ? mn : mn + random(mx - mn); }
void randomSeed(unsigned long s) { gerador.seed(s); }

char *dtostrf(double v, signed char largura, unsigned char decimais, char *s) {
  std::sprintf(s, "%*.*f", largura, decimais, v);
  return s;
}
static char *emBase(unsigned long long v, char *s, int base, bool negativo) {
  char tmp[70];
  int n = 0;
  if (base < 2 || base > 36) base = 10;
  do {
    int d = (int)(v % base);
    tmp[n++] = (char)(d < 10 ? '0' + d : 'a' + d - 10);
    v /= base;
  } while (v);
  int k = 0;
  if (negativo) s[k++] = '-';
  while (n) s[k++] = tmp[--n];
  s[k] = 0;
  return s;
}
char *itoa(int v, char *s, int b) { return ltoa(v, s, b); }
char *ltoa(long v, char *s, int b) {
  return b == 10 && v < 0 ? emBase((unsigned long long)(-(long long)v), s, b, true) : emBase((unsigned long)v, s, b, false);
}
char *utoa(unsigned v, char *s, int b) { return emBase(v, s, b, false); }
char *ultoa(unsigned long v, char *s, int b) { return emBase(v, s, b, false); }

// =====================================================================
// String
// =====================================================================
static std::string numeroEmTexto(unsigned long long v, int base, bool negativo) {
  char b[72];
  emBase(v, b, base, negativo);
  return b;
}
String::String(unsigned char v, unsigned char b) : s_(numeroEmTexto(v, b, false)) {}
String::String(int v, unsigned char b) : String((long long)v, b) {}
String::String(unsigned int v, unsigned char b) : s_(numeroEmTexto(v, b, false)) {}
String::String(long v, unsigned char b) : String((long long)v, b) {}
String::String(unsigned long v, unsigned char b) : s_(numeroEmTexto(v, b, false)) {}
String::String(long long v, unsigned char b)
    : s_(b == 10 && v < 0 ? numeroEmTexto((unsigned long long)(-v), 10, true) : numeroEmTexto((unsigned long long)v, b, false)) {}
String::String(unsigned long long v, unsigned char b) : s_(numeroEmTexto(v, b, false)) {}
String::String(float v, unsigned char d) : String((double)v, d) {}
String::String(double v, unsigned char d) {
  char b[64];
  std::snprintf(b, sizeof b, "%.*f", d, v);
  s_ = b;
}
bool String::equalsIgnoreCase(const String &o) const {
  if (s_.size() != o.s_.size()) return false;
  for (size_t i = 0; i < s_.size(); i++)
    if (tolower((unsigned char)s_[i]) != tolower((unsigned char)o.s_[i])) return false;
  return true;
}
void String::trim() {
  size_t a = 0, z = s_.size();
  while (a < z && isspace((unsigned char)s_[a])) a++;
  while (z > a && isspace((unsigned char)s_[z - 1])) z--;
  s_ = s_.substr(a, z - a);
}
void String::replace(const String &de, const String &para) {
  if (de.s_.empty()) return;
  size_t p = 0;
  while ((p = s_.find(de.s_, p)) != std::string::npos) {
    s_.replace(p, de.s_.size(), para.s_);
    p += para.s_.size();
  }
}

// =====================================================================
// Print / Stream / Serial
// =====================================================================
size_t Print::imprimirNumero(unsigned long long v, int base) { return write(numeroEmTexto(v, base, false).c_str()); }
size_t Print::imprimirSinal(long long v, int base) {
  if (base == 10 && v < 0) return write(numeroEmTexto((unsigned long long)(-v), 10, true).c_str());
  if (base != 10 && v < 0) return imprimirNumero((unsigned long long)(uint32_t)v, base);
  return imprimirNumero((unsigned long long)v, base);
}
size_t Print::print(double v, int d) {
  if (std::isnan(v)) return write("nan");
  if (std::isinf(v)) return write("inf");
  char b[64];
  std::snprintf(b, sizeof b, "%.*f", d, v);
  return write(b);
}
size_t Print::printf(const char *fmt, ...) {
  char b[1024];
  va_list a;
  va_start(a, fmt);
  int n = std::vsnprintf(b, sizeof b, fmt, a);
  va_end(a);
  if (n < 0) return 0;
  return write((const uint8_t *)b, std::min<size_t>((size_t)n, sizeof b - 1));
}

int Stream::lerComEspera() {
  unsigned long inicio = millis();
  do {
    int c = read();
    if (c >= 0) return c;
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  } while (millis() - inicio < timeout_);
  return -1;
}
size_t Stream::readBytes(char *buf, size_t n) {
  size_t k = 0;
  while (k < n) {
    int c = lerComEspera();
    if (c < 0) break;
    buf[k++] = (char)c;
  }
  return k;
}
size_t Stream::readBytesUntil(char fim, char *buf, size_t n) {
  size_t k = 0;
  while (k < n) {
    int c = lerComEspera();
    if (c < 0 || c == fim) break;
    buf[k++] = (char)c;
  }
  return k;
}
String Stream::readString() {
  std::string r;
  int c;
  while ((c = lerComEspera()) >= 0) r += (char)c;
  return String(r);
}
String Stream::readStringUntil(char fim) {
  std::string r;
  int c;
  while ((c = lerComEspera()) >= 0 && c != fim) r += (char)c;
  return String(r);
}
long Stream::parseInt() {
  int c;
  while ((c = peek()) >= 0 && !(isdigit(c) || c == '-')) read();
  std::string r;
  while ((c = peek()) >= 0 && (isdigit(c) || (c == '-' && r.empty()))) r += (char)read();
  return atol(r.c_str());
}
float Stream::parseFloat() {
  int c;
  while ((c = peek()) >= 0 && !(isdigit(c) || c == '-' || c == '.')) read();
  std::string r;
  while ((c = peek()) >= 0 && (isdigit(c) || c == '.' || (c == '-' && r.empty()))) r += (char)read();
  return (float)atof(r.c_str());
}
bool Stream::find(const char *alvo) {
  size_t i = 0, n = strlen(alvo);
  int c;
  while (i < n && (c = lerComEspera()) >= 0) i = (c == alvo[i]) ? i + 1 : (c == alvo[0] ? 1 : 0);
  return i == n;
}

HardwareSerial Serial;
int HardwareSerial::available() { std::lock_guard<std::mutex> g(trava); return (int)entradaSerial.size(); }
int HardwareSerial::read() {
  std::lock_guard<std::mutex> g(trava);
  if (entradaSerial.empty()) return -1;
  char c = entradaSerial.front();
  entradaSerial.pop_front();
  return (unsigned char)c;
}
int HardwareSerial::peek() {
  std::lock_guard<std::mutex> g(trava);
  return entradaSerial.empty() ? -1 : (unsigned char)entradaSerial.front();
}
size_t HardwareSerial::write(uint8_t c) {
  bufferSerial += (char)c;
  if (c == '\n') descarregarSerial(false);
  if (bufferSerial.size() > 4096) descarregarSerial(true);
  return 1;
}
void HardwareSerial::flush() { descarregarSerial(true); }

// =====================================================================
// main
// =====================================================================
int main() {
#ifdef _WIN32
  _setmode(_fileno(stdin), _O_BINARY);
  _setmode(_fileno(stdout), _O_BINARY);
#endif
  for (int i = 0; i < 100; i++) forcado[i] = -1;
  inicioReal = Relogio::now();
  utcInicioMs = std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::system_clock::now().time_since_epoch()).count();
  if (const char *v = std::getenv("ORIKI_VELOCIDADE")) velocidade = std::max(0.1, std::atof(v));
  if (const char *t = std::getenv("ORIKI_TEMPERATURA")) temperatura = (float)std::atof(t);
  {
    std::ifstream f(sim::caminhoDados("rtc.txt"));
    if (!(f >> ajusteRtc)) ajusteRtc = 0;
  }
  std::thread(lerEntrada).detach();
  sim::evento(std::string("\"t\":\"inicio\",\"placa\":\"") +
#ifdef ORIKI_PLACA_UNO
              "uno"
#else
              "esp32"
#endif
              + "\",\"velocidade\":" + std::to_string(velocidade));

  setup();
  for (;;) {
    loop();
    descarregarSerial(true);
    std::this_thread::sleep_for(std::chrono::microseconds(300));
  }
}
